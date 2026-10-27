import copy
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ci_inputs

D = ci_inputs.dependencies
TARGET = next(name for name, (system, architectures, _) in D.PLATFORMS.items()
              if platform.system() == system and platform.machine() in architectures)


class CiInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.git("config", "core.autocrlf", "false")
        self.git("config", "user.name", "SDK fixture")
        self.git("config", "user.email", "sdk@example.invalid")
        (self.root / "tools").mkdir()
        (self.root / "tools/fixture.txt").write_text("producer infrastructure\n")
        (self.root / "recipe.txt").write_text("build recipe\n")
        (self.root / "consumer.txt").write_text("consumer contract\n")
        (self.root / ".gitignore").write_text("artifacts/\n")
        (self.root / ".gitmodules").write_text('[submodule "fixture"]\n path = 3rdparty/fixture\n url = https://example.invalid/source.git\n')
        self.git("add", ".")
        self.git("update-index", "--add", "--cacheinfo", "160000", "a" * 40, "3rdparty/fixture")
        self.git("commit", "-qm", "Native input fixture")
        self.output = self.root / "artifacts/SDK Кино with spaces"
        self.output.parent.mkdir()
        self.archive = self.root / "artifacts/sdk.zip"
        self.specification = {
            "status": "ready", "always": True, "roots": ["3rdparty/fixture"],
            "sources": {"3rdparty/fixture": {"revision": "a" * 40, "license": "Apache-2.0",
                "notices": ["LICENSE"], "requires": [], "unusedSubmodules": {}}},
            "inputs": ["recipe.txt"], "watch": ["recipe.txt"], "verificationInputs": ["consumer.txt"],
            "targets": {TARGET: {"toolchains": {"cc": {"command": ["cc", "--version"], "pattern": "^fixture-v1$"}},
                "environment": {}, "flags": {}, "command": ["fixture"], "verifyCommand": ["fixture"], "timeoutSeconds": 10}},
        }
        self.framework = patch.object(D, "FRAMEWORK_INPUTS", ("tools",))
        self.framework.start(); self.addCleanup(self.framework.stop)
        self.registry = patch.object(D, "registry", return_value={"fixture": self.specification})
        self.registry.start(); self.addCleanup(self.registry.stop)
        inputs = {"schemaVersion": 1, "artifactSchema": 1, "component": "fixture", "platform": TARGET,
            "specification": self.specification, "files": D.input_files(self.root, self.specification),
            "toolchains": {"cc": "fixture-v1"}, "offlineEnvironment": D.OFFLINE,
            "host": {"system": platform.system(), "architecture": platform.machine()},
            "sources": {"3rdparty/fixture": {"revision": "a" * 40, "tree": "b" * 40,
                "url": "https://example.invalid/source.git", "archiveSha256": "c" * 64}}}
        self.payload = b"source-built native SDK"
        self.manifest = {"schemaVersion": 1, "result": "success", "inputs": inputs,
            "key": hashlib.sha256(D.canonical(inputs)).hexdigest(),
            "verifiedSourceCommit": self.git("rev-parse", "HEAD"), "verifiedSourceTree": self.git("rev-parse", "HEAD^{tree}"),
            "verifiedLocalChanges": False, "runId": "12", "runAttempt": "1", "cacheHit": True,
            "buildSourceCommit": "d" * 40, "buildSourceTree": "e" * 40,
            "verificationInputs": D.input_files(self.root, self.specification, verification=True),
            "files": {"payload/library.bin": {"mode": 0o644 if sys.platform == "win32" else 0o755,
                                                "sha256": hashlib.sha256(self.payload).hexdigest()}}}

    def git(self, *arguments):
        return subprocess.check_output(["git", *arguments], cwd=self.root, text=True).strip()

    def write_archive(self, manifest=None, payload=None, extra=None):
        with zipfile.ZipFile(self.archive, "w") as package:
            package.writestr("build-manifest.json", json.dumps(manifest or self.manifest))
            package.writestr("payload/library.bin", self.payload if payload is None else payload)
            if extra:
                package.writestr(*extra)

    def import_sdk(self):
        return ci_inputs.import_dependency(self.archive, self.output, component="fixture", target=TARGET,
                                           run_id=12, producer_attempt=1, root=self.root)

    def test_fresh_verification_imports_exact_bytes_and_retains_cached_build_provenance(self):
        self.write_archive()
        before = D.digest(self.archive)
        payload = self.import_sdk()
        self.assertEqual((payload / "library.bin").read_bytes(), self.payload)
        self.assertEqual(json.loads((self.output / "build-manifest.json").read_text()), self.manifest)
        self.assertEqual(D.digest(self.archive), before)
        self.assertFalse(any(p.name.startswith(".sdk-import-") for p in self.output.iterdir()))
        if sys.platform != "win32":
            self.assertTrue((payload / "library.bin").stat().st_mode & 0o111)

    def test_stale_source_producer_and_changed_first_party_inputs_fail_before_extraction(self):
        for delta in ({"verifiedSourceCommit": "f" * 40}, {"verifiedSourceTree": "f" * 40},
                      {"verifiedLocalChanges": True}, {"runId": "13"}, {"runAttempt": "2"}, {"result": "failure"}):
            with self.subTest(delta=delta):
                self.write_archive(self.manifest | delta)
                with self.assertRaises(ValueError): self.import_sdk()
                self.assertFalse(self.output.exists())
        self.write_archive()
        for name in ("recipe.txt", "consumer.txt"):
            path = self.root / name; original = path.read_bytes(); path.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "inputs differ"): self.import_sdk()
            self.assertFalse(self.output.exists()); path.write_bytes(original)

    def test_source_pins_platform_exports_and_toolchain_claims_cannot_be_substituted(self):
        for category, delta in (("sources", {"3rdparty/fixture": {"revision": "f" * 40}}),
                                ("platform", "wrong-os"), ("toolchains", {"cc": "unreviewed"}),
                                ("offlineEnvironment", {}), ("specification", {})):
            with self.subTest(category=category):
                manifest = copy.deepcopy(self.manifest); manifest["inputs"][category] = delta
                manifest["key"] = hashlib.sha256(D.canonical(manifest["inputs"])).hexdigest()
                self.write_archive(manifest)
                with self.assertRaises(ValueError): self.import_sdk()
                self.assertFalse(self.output.exists())

    def test_corruption_escaping_members_and_failed_copy_leave_no_owned_output(self):
        for options in ({"payload": b"corrupt"}, {"extra": ("../escaped", b"escape")}):
            self.write_archive(**options)
            with self.assertRaises(ValueError): self.import_sdk()
            self.assertFalse(self.output.exists())
        self.write_archive()
        with patch.object(D, "unpack", side_effect=OSError("interrupted copy")):
            with self.assertRaises(OSError): self.import_sdk()
        self.assertFalse(self.output.exists())
        self.assertFalse((self.root / "escaped").exists())

    def test_existing_output_and_payload_changed_after_validation_are_not_adopted(self):
        self.write_archive(); self.output.mkdir(); (self.output / "user.txt").write_bytes(b"preserve")
        with self.assertRaises(FileExistsError): self.import_sdk()
        self.assertEqual((self.output / "user.txt").read_bytes(), b"preserve")
        shutil.rmtree(self.output)
        original = D.unpack
        def mutate(archive, destination, expected):
            result = original(archive, destination, expected)
            (destination / "payload/library.bin").write_bytes(b"changed after verification")
            return result
        with patch.object(D, "unpack", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "changed during import"): self.import_sdk()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
