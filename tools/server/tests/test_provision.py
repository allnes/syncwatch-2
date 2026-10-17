import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile


SPEC = importlib.util.spec_from_file_location("server_check", Path(__file__).resolve().parents[1] / "check.py")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class ProvisioningTests(unittest.TestCase):
    def test_nonofficial_or_insecure_sdk_source_is_rejected_without_download(self):
        for url in ("http://builds.dotnet.microsoft.com/sdk.zip", "https://example.invalid/sdk.zip", "https://user:secret@builds.dotnet.microsoft.com/sdk.zip"):
            spec = {"sdkVersion": "10.0.402", "sources": {"win-x64": {"url": url, "sha512": "a" * 128}}}
            with tempfile.TemporaryDirectory() as directory, patch.object(CHECK.urllib.request, "urlretrieve") as download:
                with self.assertRaises(ValueError):
                    CHECK.provision(spec, "win-x64", Path(directory))
                download.assert_not_called()

    def test_corrupt_archive_cannot_be_extracted_or_reused(self):
        spec = {"sdkVersion": "10.0.402", "sources": {"win-x64": {"url": "https://builds.dotnet.microsoft.com/sdk.zip", "sha512": "a" * 128}}}
        def download(_url, path):
            path.write_bytes(b"corrupt")
        with tempfile.TemporaryDirectory() as directory, patch.object(CHECK.urllib.request, "urlretrieve", side_effect=download):
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                CHECK.provision(spec, "win-x64", Path(directory))
            self.assertFalse(any(Path(directory).iterdir()))

    def test_verified_zip_cannot_write_outside_extraction_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "fixture.zip"
            with zipfile.ZipFile(fixture, "w") as archive:
                archive.writestr("../outside", b"escape")
            spec = {"sdkVersion": "10.0.402", "sources": {"win-x64": {"url": "https://builds.dotnet.microsoft.com/sdk.zip", "sha512": hashlib.sha512(fixture.read_bytes()).hexdigest()}}}
            def download(_url, path):
                path.write_bytes(fixture.read_bytes())
            with patch.object(CHECK.urllib.request, "urlretrieve", side_effect=download), self.assertRaisesRegex(ValueError, "leaves extraction"):
                CHECK.provision(spec, "win-x64", root / "tools")
            self.assertFalse((root / "outside").exists())
            self.assertFalse(any((root / "tools").iterdir()))


if __name__ == "__main__":
    unittest.main()
