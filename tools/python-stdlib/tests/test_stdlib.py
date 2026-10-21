"""Check the actual reviewed source/payload and rejection of changed cached distributions."""

import copy
import io
from pathlib import Path
import platform
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stdlib_profile import COMPONENT, ROOT, analyze, profile_data
from stdlib_package import payload_files, read_snapshot, verify


class StdlibTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = profile_data()
        # prepare is deliberately required: no implicit source downloads inside tests.
        target = {"Darwin": "macos-arm64", "Windows": "windows-x64", "Linux": "linux-x64"}[platform.system()]
        cls.files = read_snapshot(ROOT / "artifacts/dependencies" / COMPONENT / target / "cpython.tar", cls.profile["source"])
        cls.payload = payload_files(cls.files, cls.profile)

    def write_payload(self, root):
        for name, content in self.payload.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    def test_runtime_zip_preserves_exact_sources_and_stored_metadata(self):
        with zipfile.ZipFile(io.BytesIO(self.payload["stdlib.zip"])) as archive:
            expected = {name.removeprefix("Lib/"): data for name, data in self.files.items() if name.startswith("Lib/")}
            self.assertEqual(sorted(archive.namelist()), sorted(expected))
            for info in archive.infolist():
                self.assertEqual(archive.read(info), expected[info.filename])
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.external_attr >> 16, 0o100644)

    def test_full_notice_and_original_source_archive(self):
        for name in self.profile["source"]["notices"]:
            self.assertEqual(self.payload["notices/cpython/" + name], self.files[name])
        with zipfile.ZipFile(io.BytesIO(self.payload["sources.zip"])) as archive:
            self.assertEqual(set(archive.namelist()), set(self.files))
            for name, data in self.files.items():
                self.assertEqual(archive.read(name), data)

    def test_unreviewed_import_is_rejected(self):
        files = dict(self.files)
        files["Lib/encodings/utf_8.py"] += b"\nimport ssl\n"
        with self.assertRaisesRegex(ValueError, "unreviewed interface"):
            analyze(files, self.profile)

    def test_changed_source_or_notice_does_not_match_profile(self):
        for name in ("Lib/encodings/utf_8.py", "LICENSE"):
            with self.subTest(name=name):
                files = dict(self.files)
                files[name] += b"\n"
                with self.assertRaisesRegex(ValueError, "reviewed source profile"):
                    payload_files(files, self.profile)

    def test_changed_archive_digest_is_rejected(self):
        profile = copy.deepcopy(self.profile)
        profile["stdlibSha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "reviewed source profile"):
            payload_files(self.files, profile)

    def test_valid_payload_then_corrupt_cached_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_payload(root)
            verify(root, self.payload)
            (root / "stdlib.zip").write_bytes(self.payload["stdlib.zip"][:-1] + b"x")
            with self.assertRaisesRegex(ValueError, "differs"):
                verify(root, self.payload)

    def test_missing_notice_and_extra_module_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_payload(root)
            (root / "notices/cpython/LICENSE").unlink()
            with self.assertRaisesRegex(ValueError, "missing or unexpected"):
                verify(root, self.payload)
            (root / "notices/cpython/LICENSE").write_bytes(self.files["LICENSE"])
            (root / "sitecustomize.py").write_bytes(b"pass\n")
            with self.assertRaisesRegex(ValueError, "differs"):
                verify(root, self.payload)

    def test_symlink_payload_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_payload(root)
            path = root / "stdlib.zip"
            path.unlink()
            try:
                path.symlink_to(root / "sources.zip")
            except OSError:
                self.skipTest("This account cannot create symbolic links")
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                verify(root, self.payload)


if __name__ == "__main__":
    unittest.main()
