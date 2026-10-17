import hashlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile


SPEC = importlib.util.spec_from_file_location("jdk_tool", Path(__file__).resolve().parents[1] / "jdk.py")
jdk = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jdk)


class JdkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name);self.sdk = self.root / "original";self.sdk.mkdir()
        for name in ["LICENSE", "ADDITIONAL_LICENSE_INFO", "ASSEMBLY_EXCEPTION"]:
            p = self.sdk / "vendor/Home/legal/java.base" / name;p.parent.mkdir(parents=True, exist_ok=True);p.write_text("Fixture developer legal text " + name)
        p = self.sdk / "vendor/Home/bin/javac";p.parent.mkdir(parents=True);p.write_text("Fixture compiler, never executed")
        self.spec = {"version": "fixture", "javacVersion": "javac fixture", "targets": {"linux-x64": {
            "url": "https://github.com/adoptium/temurin21-binaries/releases/download/fixture/sdk.tar.gz",
            "sha256": "0" * 64, "home": "vendor/Home", "inventorySha256": jdk.inventory_digest(jdk.inventory(self.sdk))}}}

    def archive(self):
        archive = self.root / "sdk.tar.gz"
        with tarfile.open(archive, "w:gz") as target:target.add(self.sdk / "vendor", arcname="vendor")
        self.spec["targets"]["linux-x64"]["sha256"] = jdk.sha(archive)
        return archive

    def test_verified_local_provision_and_reuse_preserve_legal_files(self):
        archive = self.archive()
        with patch.object(jdk.subprocess, "check_output", return_value="javac fixture\n"), patch.object(jdk.urllib.request, "urlretrieve", side_effect=AssertionError("No network")):
            first = jdk.provision(self.spec, "linux-x64", self.root / "installed", archive)
            second = jdk.provision(self.spec, "linux-x64", self.root / "installed", archive)
        self.assertEqual(first, second)
        self.assertEqual((first / "legal/java.base/LICENSE").read_text(), "Fixture developer legal text LICENSE")

    def test_wrong_archive_checksum_never_installs(self):
        archive = self.archive();archive.write_bytes(archive.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            jdk.provision(self.spec, "linux-x64", self.root / "installed", archive)
        self.assertFalse((self.root / "installed/temurin-fixture-linux-x64").exists())

    def test_cached_sdk_tampering_is_detected_before_compiler_execution(self):
        (self.sdk / "vendor/Home/bin/javac").write_text("changed compiler")
        with patch.object(jdk.subprocess, "check_output") as execute, self.assertRaisesRegex(ValueError, "complete vendor archive inventory"):
            jdk.verify(self.sdk, self.spec, "linux-x64")
        execute.assert_not_called()

    def test_missing_legal_text_is_not_an_acceptable_sdk(self):
        (self.sdk / "vendor/Home/legal/java.base/LICENSE").unlink()
        self.spec["targets"]["linux-x64"]["inventorySha256"] = jdk.inventory_digest(jdk.inventory(self.sdk))
        with self.assertRaisesRegex(ValueError, "legal notices"):
            jdk.verify(self.sdk, self.spec, "linux-x64")

    def test_compiler_version_must_match_the_pin(self):
        with patch.object(jdk.subprocess, "check_output", return_value="javac other\n"), self.assertRaisesRegex(ValueError, "exact version pin"):
            jdk.verify(self.sdk, self.spec, "linux-x64")

    def test_unapproved_download_origin_is_rejected(self):
        self.spec["targets"]["linux-x64"]["url"] = "https://example.invalid/sdk.tar.gz"
        with patch.object(jdk.urllib.request, "urlretrieve") as download, self.assertRaisesRegex(ValueError, "official vendor"):
            jdk.provision(self.spec, "linux-x64", self.root / "installed")
        download.assert_not_called()

    def test_unsafe_zip_and_tar_paths_cannot_leave_the_installation(self):
        for kind in ["zip", "tar"]:
            archive = self.root / ("unsafe." + kind);out = self.root / ("out-" + kind);out.mkdir()
            if kind == "zip":
                with zipfile.ZipFile(archive, "w") as data:data.writestr("../escape", b"not allowed")
            else:
                with tarfile.open(archive, "w") as data:
                    member = tarfile.TarInfo("../escape");member.size = 1;data.addfile(member, io.BytesIO(b"x"))
            with self.subTest(kind=kind), self.assertRaises((ValueError, tarfile.TarError)):
                jdk.extract(archive, out)
            self.assertFalse((self.root / "escape").exists())


if __name__ == "__main__":
    unittest.main()
