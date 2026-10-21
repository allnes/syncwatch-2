"""Source, independent-oracle, input-boundary and restored-payload regressions."""

import copy
import io
from pathlib import Path
import platform
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unicode_profile import COMPONENT, ROOT, original_archive, profile_data, read_sources, validate
from unicode_oracle import UCD, interchange, numeric_rows, properties, tables, transcript
from generate_unicode import Ports
from native_unicode import fixture
from unicode_build import materialize, payload_files, verify_files


class UnicodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = profile_data()
        target = {"Darwin": "macos-arm64", "Linux": "linux-x64", "Windows": "windows-x64"}[platform.system()]
        directory = ROOT / "artifacts/dependencies" / COMPONENT / target
        paths = {name: directory / (Path(source["path"]).name + ".tar") for name, source in cls.profile["sources"].items()}
        cls.sources = read_sources(paths, cls.profile)
        cls.header = cls.sources["cpython"]["Objects/unicodetype_db.h"]
        cls.payload = payload_files(cls.sources, cls.profile, cls.header, {"testFixture": True})

    def test_original_sources_full_notices_and_unchanged_kotlin_pin(self):
        validate(self.sources, self.profile)
        with zipfile.ZipFile(io.BytesIO(original_archive(self.sources))) as archive:
            self.assertEqual(len(archive.namelist()), 22)
            for origin, files in self.sources.items():
                for name, data in files.items():
                    self.assertEqual(archive.read(origin + "/" + name), data)
        for origin, source in self.profile["sources"].items():
            for notice in source["notices"]:
                self.assertEqual(self.payload["notices/" + source["path"].split("/")[-1] + "/" + notice], self.sources[origin][notice])
        import subprocess
        self.assertEqual(subprocess.check_output(["git", "rev-parse", "HEAD:3rdparty/unicode-data"], cwd=ROOT, text=True).strip(),
                         "84a95001ba850554e65234dde62cbdb0ad41105a")

    def test_full_original_and_independent_transcript(self):
        self.assertEqual(transcript(self.header, self.sources["unicode"]), self.profile["transcript"])
        values, spaces, breaks = properties(self.sources["unicode"])
        self.assertEqual(values[0xBD], 0.5)
        self.assertEqual(values[0x0F33], -0.5)
        self.assertEqual(values[0x4EDF], 1000.0)
        self.assertIn(0x202F, spaces)
        self.assertNotIn(0x200B, spaces)
        self.assertIn(0x2028, breaks)
        self.assertNotIn(0x202F, breaks)

    def test_original_range_expansion_and_explicit_derived_interchange(self):
        rows = numeric_rows(self.sources["unicode"])
        self.assertEqual(len(rows), 73)
        self.assertTrue(all((cp, "kAccountingNumeric", "3") in rows for cp in range(0x53C1, 0x53C4)))
        self.assertEqual(self.payload["derived/Unihan_NumericValues.txt"], interchange(self.sources["unicode"]))
        changed = dict(self.sources["unicode"])
        path = UCD + "Unihan/kAccountingNumeric.txt"
        for bad in (b"53C3..53C1\t3\n", b"110000\t1\n", b"4EDF\t1000\n4EDF\t1000\n"):
            changed[path] = bad
            with self.assertRaises(ValueError):
                numeric_rows(changed)

    def test_ports_reject_unknown_versions_inputs_and_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "header.h"
            ports = Ports(self.sources["unicode"], destination)
            for name, version in (("UnicodeData%s.txt", "3.2.0"), ("Unknown%s.txt", "15.0.0")):
                with self.assertRaisesRegex(ValueError, "Unreviewed"):
                    ports.read(name, version)
            with ports.read("UnicodeData%s.txt", "15.0.0") as data:
                self.assertTrue(data.read(5))
            with self.assertRaisesRegex(ValueError, "Unreviewed"):
                ports.read("UnicodeData%s.txt", "15.0.0")
            for name, mode in (("../escape.h", "w"), ("Objects/unicodetype_db.h", "a")):
                with self.assertRaisesRegex(ValueError, "Unreviewed"):
                    ports.write(name, mode)
            with ports.write("Objects/unicodetype_db.h", "w") as output:
                output.write("original\n")
            self.assertEqual(destination.read_bytes(), b"original\n")
            with self.assertRaisesRegex(ValueError, "Unreviewed"):
                ports.write("Objects/unicodetype_db.h", "w")

    def test_missing_or_ambiguous_native_original_fragments(self):
        content, hashes = fixture(self.sources["cpython"], self.header)
        self.assertIn(self.header, content)
        self.assertEqual(set(hashes), {"publicType", "recordType", "lookup"})
        for replacement in (b"", self.sources["cpython"]["Include/unicodeobject.h"] * 2):
            changed = dict(self.sources["cpython"], **{"Include/unicodeobject.h": replacement})
            with self.assertRaisesRegex(ValueError, "ambiguous or missing"):
                fixture(changed, self.header)

    def test_invalid_table_bounds_and_modified_oracle_rejected(self):
        with self.assertRaisesRegex(ValueError, "out of bounds"):
            tables(self.header.replace(b"#define SHIFT 7", b"#define SHIFT 6"))
        changed = self.header.replace(b"{0, 0, 0, 0, 0, 0},", b"{1, 0, 0, 0, 0, 0},", 1)
        self.assertNotEqual(transcript(changed, self.sources["unicode"]), self.profile["transcript"])

    def test_changed_source_and_notice_rejected(self):
        for origin, name in (("unicode", "LICENSE"), ("cpython", "Include/unicodeobject.h"), ("unicode", UCD + "UnicodeData.txt")):
            changed = copy.deepcopy(self.sources)
            changed[origin][name] += b"\n"
            with self.assertRaisesRegex(ValueError, "source or full notice"):
                validate(changed, self.profile)

    def test_changed_cached_header_proof_and_missing_notice(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialize(root, self.payload)
            verify_files(root, self.payload)
            for name in ("include/unicodetype_db.h", "build-report.json", "notices/python-unicode-data/LICENSE"):
                path = root / name
                path.write_bytes(path.read_bytes() + b"\n")
                with self.assertRaisesRegex(ValueError, "differs"):
                    verify_files(root, self.payload)
                path.write_bytes(self.payload[name])
            (root / "notices/cpython/LICENSE").unlink()
            with self.assertRaisesRegex(ValueError, "missing or unexpected"):
                verify_files(root, self.payload)

    def test_extra_and_symlink_payload_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialize(root, self.payload)
            extra = root / "unknown"
            extra.write_bytes(b"extra")
            with self.assertRaisesRegex(ValueError, "differs"):
                verify_files(root, self.payload)
            extra.unlink()
            try:
                extra.symlink_to(root / "sources.zip")
            except OSError:
                self.skipTest("This account cannot create symbolic links")
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                verify_files(root, self.payload)


if __name__ == "__main__":
    unittest.main()
