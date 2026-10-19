import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import zlib_build as zlib
import toolchain


class ZlibBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.files = {"CMakeLists.txt": b"set(ZLIB_SRCS fixture.c)\n", "fixture.c": b"/* Fixture original source. */\n",
                      "zlib.h": b'#define ZLIB_VERSION "fixture"\n', "zconf.h": b"/* Original configuration */\n",
                      "LICENSE": b"Complete original fixture license\n"}
        self.source = {"revision": "a" * 40, "notices": ["LICENSE", "zlib.h"],
                       "files": {n: zlib.digest(d) for n, d in self.files.items()}}
        self.profile = {"version": "fixture", "source": self.source, "compileSources": ["fixture.c"],
                        "sourceArchiveSha256": zlib.digest(zlib.archive_bytes(self.files)), "probeCases": ["fixtureRoundTrip"]}
        self.probe = {"version": "fixture", "pointerBits": 64, "cases": ["fixtureRoundTrip"]}
        self.sdk = {"target": "linux-x64", "compiler": "fixture SDK"}

    def write(self, directory, files):
        for name, data in files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def snapshot(self, revision=None, extra=None):
        path = self.root / "source.tar"
        with tarfile.open(path, "w", format=tarfile.PAX_FORMAT, pax_headers={"comment": revision or self.source["revision"]}) as archive:
            for name, data in self.files.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
            if extra is not None:
                archive.addfile(extra)
        return path

    def test_exact_source_directory_and_pinned_export_match(self):
        self.write(self.root / "source", self.files)
        self.assertEqual(zlib.read_snapshot(self.root / "source", self.source), self.files)
        self.assertEqual(zlib.read_snapshot(self.snapshot(), self.source), self.files)

    def test_changed_missing_extra_source_and_notice_are_rejected(self):
        self.write(self.root / "source", self.files | {"LICENSE": b"modified"})
        with self.assertRaisesRegex(ValueError, "digest changed"):
            zlib.read_snapshot(self.root / "source", self.source)
        self.write(self.root / "source", self.files)
        (self.root / "source/fixture.c").unlink()
        with self.assertRaisesRegex(ValueError, "file inventory"):
            zlib.read_snapshot(self.root / "source", self.source)
        self.write(self.root / "source", self.files | {"unreviewed.c": b"extra"})
        with self.assertRaisesRegex(ValueError, "file inventory"):
            zlib.read_snapshot(self.root / "source", self.source)

    def test_source_exports_reject_wrong_commit_duplicate_link_and_unsafe_names(self):
        with self.assertRaisesRegex(ValueError, "Git revision"):
            zlib.read_snapshot(self.snapshot("b" * 40), self.source)
        link = tarfile.TarInfo("link")
        link.type, link.linkname = tarfile.SYMTYPE, "LICENSE"
        for item in [link, tarfile.TarInfo("LICENSE"), tarfile.TarInfo("../escape"), tarfile.TarInfo("C:escape")]:
            with self.subTest(name=item.name), self.assertRaises(ValueError):
                zlib.read_snapshot(self.snapshot(extra=item), self.source)

    def test_upstream_compiled_source_inventory_version_and_archive_are_required(self):
        zlib.validate_sources(self.files, self.profile)
        for files, profile in [(self.files, self.profile | {"compileSources": []}),
                               (self.files | {"zlib.h": b"changed"}, self.profile),
                               (self.files, self.profile | {"sourceArchiveSha256": "0" * 64})]:
            with self.assertRaises(ValueError):
                zlib.validate_sources(files, profile)

    def test_probe_rejects_wrong_version_architecture_missing_cases_and_extra_fields(self):
        zlib.validate_probe(self.probe, self.profile)
        for changed in [{"version": "wrong"}, {"pointerBits": 32}, {"pointerBits": True}, {"cases": []}, {"unexpected": True}]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                zlib.validate_probe(self.probe | changed, self.profile)

    def payload(self):
        return zlib.expected_payload(self.files, self.profile, self.sdk, b"!<arch>\nfixture", b"Configured fixture header\n", self.probe)

    def test_source_archive_notices_sdk_and_binary_are_bound_in_report(self):
        expected = self.payload()
        report = json.loads(expected["build-report.json"])
        self.assertEqual(expected["sources.zip"], zlib.archive_bytes(self.files))
        self.assertEqual(expected["notices/zlib/LICENSE"], self.files["LICENSE"])
        self.assertEqual(report["sdk"], self.sdk)
        self.assertEqual(report["files"]["lib/libzlibstatic.a"], zlib.digest(b"!<arch>\nfixture"))
        self.assertIs(report["syncplayRuntimeReady"], False)
        with self.assertRaisesRegex(ValueError, "static native archive"):
            zlib.expected_payload(self.files, self.profile, self.sdk, b"shared ELF file", b"header", self.probe)

    def test_cache_revalidation_rejects_replaced_library_header_notice_and_report(self):
        expected = self.payload()
        for name in ["lib/libzlibstatic.a", "include/zlib.h", "include/zconf.h", "notices/zlib/LICENSE", "build-report.json"]:
            self.write(self.root / "payload", expected)
            zlib.verify_files(self.root / "payload", expected)
            (self.root / "payload" / name).write_bytes(b"modified")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "differs"):
                zlib.verify_files(self.root / "payload", expected)

    def test_missing_output_and_unexpected_runtime_dll_are_rejected(self):
        expected = self.payload()
        self.write(self.root / "payload", expected)
        (self.root / "payload/include/zconf.h").unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            zlib.verify_files(self.root / "payload", expected)
        self.write(self.root / "payload", expected | {"runtime.dll": b"unreviewed runtime"})
        with self.assertRaisesRegex(ValueError, "differs"):
            zlib.verify_files(self.root / "payload", expected)

    def test_generated_configuration_is_plainly_marked(self):
        path = self.root / "zconf.h"
        path.write_bytes(b"original header\n")
        header = zlib.configuration_header(path)
        self.assertIn(b"configuration differs from original zconf.h", header)
        self.assertTrue(header.endswith(path.read_bytes()))

    def test_profile_rejects_graph_or_license_drift(self):
        profile = zlib.profile_data()
        registry = json.loads((zlib.ROOT / "tools/dependencies/components.json").read_text())
        self.write(self.root, {"tools/compression/profile.json": zlib.encoded(profile),
                               "tools/dependencies/components.json": zlib.encoded(registry)})
        with patch.object(zlib, "ROOT", self.root):
            zlib.profile_data()
            registry["components"]["zlib"]["sources"][profile["source"]["path"]]["notices"] = []
            self.write(self.root, {"tools/dependencies/components.json": zlib.encoded(registry)})
            with self.assertRaisesRegex(ValueError, "registered graph"):
                zlib.profile_data()

    def test_unsupported_native_host_is_rejected_before_sdk_discovery(self):
        with patch.object(toolchain.platform, "system", return_value="Linux"), patch.object(toolchain.platform, "machine", return_value="armv7l"):
            with self.assertRaisesRegex(ValueError, "host architecture"):
                toolchain.resolve()


if __name__ == "__main__":
    unittest.main()
