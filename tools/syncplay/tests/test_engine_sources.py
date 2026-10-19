import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine_sources as engine
from source_analysis import analyze


class EngineSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.files = {"LICENSE": b"Complete fixture license\n", "README.md": b"Original fixture notice\n",
                      "syncplay/__init__.py": b"version = 'fixture'\n",
                      "syncplay/client.py": b"from twisted.internet import reactor\nclass SyncplayClient:\n def __init__(self, playerClass, ui, config):\n  self.name = config['name']\n"}
        self.specification = {"revision": "a" * 40, "files": {n: engine.digest(d) for n, d in self.files.items()},
                              "notices": ["LICENSE", "README.md"]}
        self.profile = {"version": "fixture", "source": self.specification, "standardLibraryRoots": [],
                        "archiveSha256": engine.digest(engine.archive_bytes(self.files)),
                        "analysisSha256": engine.digest(engine.encoded(analyze(self.files, [])))}

    def write(self, directory, files):
        for name, data in files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def snapshot(self, revision=None, extra=None):
        path = self.root / "snapshot.tar"
        with tarfile.open(path, "w", format=tarfile.PAX_FORMAT,
                          pax_headers={"comment": revision or self.specification["revision"]}) as archive:
            for name, data in self.files.items():
                item = tarfile.TarInfo(name)
                item.size = len(data)
                archive.addfile(item, io.BytesIO(data))
            if extra is not None:
                archive.addfile(extra)
        return path

    def test_exact_directory_and_pinned_snapshot_match(self):
        self.write(self.root / "source", self.files)
        self.assertEqual(engine.read_snapshot(self.root / "source", self.specification), self.files)
        self.assertEqual(engine.read_snapshot(self.snapshot(), self.specification), self.files)

    def test_snapshot_rejects_changed_missing_extra_sources_and_notices(self):
        for name in self.files:
            modified = self.files | {name: b"changed"}
            self.write(self.root / "source", modified)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "digest changed"):
                engine.read_snapshot(self.root / "source", self.specification)
        self.write(self.root / "source", self.files)
        (self.root / "source/LICENSE").unlink()
        with self.assertRaisesRegex(ValueError, "file inventory"):
            engine.read_snapshot(self.root / "source", self.specification)
        self.write(self.root / "source", self.files | {"extra.py": b""})
        with self.assertRaisesRegex(ValueError, "file inventory"):
            engine.read_snapshot(self.root / "source", self.specification)

    def test_archive_rejects_wrong_revision_duplicates_links_and_traversal(self):
        with self.assertRaisesRegex(ValueError, "Git revision"):
            engine.read_snapshot(self.snapshot("b" * 40), self.specification)
        link = tarfile.TarInfo("link")
        link.type, link.linkname = tarfile.SYMTYPE, "LICENSE"
        for extra in [tarfile.TarInfo("LICENSE"), link, tarfile.TarInfo("../escape"), tarfile.TarInfo("C:escape")]:
            with self.subTest(name=extra.name), self.assertRaises(ValueError):
                engine.read_snapshot(self.snapshot(extra=extra), self.specification)

    def test_source_zip_is_deterministic_and_preserves_all_original_bytes(self):
        archive = engine.archive_bytes(self.files)
        self.assertEqual(archive, engine.archive_bytes(dict(reversed(list(self.files.items())))))
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            self.assertEqual(set(package.namelist()), set(self.files))
            for info in package.infolist():
                self.assertEqual(package.read(info), self.files[info.filename])
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(info.external_attr >> 16, 0o100644)

    def test_payload_refuses_changed_analysis_or_archive_identity(self):
        expected = engine.payload_files(self.files, self.profile)
        manifest = json.loads(expected["source-manifest.json"])
        self.assertIs(manifest["runtimeReady"], False)
        for key in ["analysisSha256", "archiveSha256"]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "reviewed profile"):
                engine.payload_files(self.files, self.profile | {key: "0" * 64})

    def test_cached_output_rechecks_complete_notices_and_exact_payload(self):
        expected = engine.payload_files(self.files, self.profile)
        for name in expected:
            self.write(self.root / "payload", expected)
            engine.verify(self.root / "payload", expected)
            (self.root / "payload" / name).write_bytes(b"modified")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "differs"):
                engine.verify(self.root / "payload", expected)
        self.write(self.root / "payload", expected)
        (self.root / "payload/notices/syncplay/LICENSE").unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            engine.verify(self.root / "payload", expected)
        self.write(self.root / "payload", expected | {"runtime.exe": b"unexpected"})
        with self.assertRaisesRegex(ValueError, "differs"):
            engine.verify(self.root / "payload", expected)

    def test_profile_cannot_enable_runtime_or_change_registered_source_scope(self):
        profile = engine.profile_data()
        self.assertIs(profile["runtimeReady"], False)
        registry = json.loads((engine.ROOT / "tools/dependencies/components.json").read_text())
        self.write(self.root, {"tools/syncplay/profile.json": engine.encoded(profile),
                               "tools/dependencies/components.json": engine.encoded(registry)})
        with patch.object(engine, "ROOT", self.root):
            engine.profile_data()
            registry["components"]["syncplay-runtime"]["status"] = "ready"
            self.write(self.root, {"tools/dependencies/components.json": engine.encoded(registry)})
            with self.assertRaisesRegex(ValueError, "unresolved runtime"):
                engine.profile_data()
            registry["components"]["syncplay-runtime"]["status"] = "unavailable"
            registry["components"][engine.COMPONENT]["sources"][profile["source"]["path"]]["notices"] = []
            self.write(self.root, {"tools/dependencies/components.json": engine.encoded(registry)})
            with self.assertRaisesRegex(ValueError, "registered graph"):
                engine.profile_data()

    def test_import_analysis_records_deferred_unshipped_and_unknown_dependencies(self):
        files = self.files | {"syncplay/messages.py": b"from . import messages_en\ndef locale():\n from PySide2.QtCore import QLocale\n",
                              "syncplay/messages_en.py": b"en = {}\n",
                              "syncplay/players/__init__.py": b"from syncplay.players.vlc import VlcPlayer\n",
                              "setup.py": b"import setuptools\n"}
        result = analyze(files, [])
        self.assertEqual(result["unresolvedThirdPartyRoots"], ["PySide2", "twisted"])
        self.assertEqual(result["unresolvedBuildRoots"], ["setuptools"])
        self.assertEqual(result["unshippedInternalModules"], ["syncplay.players.vlc"])
        qt = next(s for s in result["imports"] if s["absolute"] == "PySide2.QtCore")
        self.assertEqual(qt["scope"], "locale")
        relative = next(s for s in result["imports"] if s["level"])
        self.assertEqual(relative["absolute"], "syncplay")
        self.assertEqual(relative["names"], ["messages_en"])
        self.assertIs(result["staticAnalysisOnly"], True)

    def test_callable_signatures_and_literal_config_reads_are_not_execution(self):
        result = analyze(self.files, [])
        self.assertEqual(result["signatures"]["SyncplayClient"]["__init__"], "self, playerClass, ui, config")
        self.assertEqual(result["literalConfigSubscripts"], ["name"])
        self.assertIs(result["runtimeReady"], False)

    def test_isolated_probe_rejects_external_import_network_and_process_attempts(self):
        # Attempts occur before later module assertions; no real network/process is allowed.
        for code in ["import unknown_external_library", "import socket; socket.socket()",
                     "import subprocess; subprocess.Popen(['must-not-execute'])"]:
            self.write(self.root, {"syncplay/__init__.py": (code + "\n").encode()})
            result = subprocess.run([sys.executable, "-I", "-S", "-B", str(engine.ROOT / "tools/syncplay/smoke.py"), str(self.root), "fixture"],
                                    capture_output=True, text=True, timeout=10)
            with self.subTest(code=code):
                self.assertNotEqual(result.returncode, 0)
                if "unknown" in code:
                    self.assertIn("External modules", result.stderr)
                else:
                    self.assertIn("Source-only", result.stderr)

    def test_failed_child_probe_preserves_its_diagnostic(self):
        files = {"syncplay/__init__.py": b"raise RuntimeError('fixture diagnostic')\n"}
        with self.assertRaisesRegex(ValueError, "fixture diagnostic"):
            engine.smoke(engine.archive_bytes(files), "fixture")


if __name__ == "__main__":
    unittest.main()
