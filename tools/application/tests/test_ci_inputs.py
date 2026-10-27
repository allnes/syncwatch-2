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

    def helper_fixture(self):
        from helper_archive import write_archive, write_origin
        for name in ("packages/ipc", "packages/syncplay-helper", "packages/python-startup", "contracts", "tools/bridge"):
            path = self.root / name; path.mkdir(parents=True, exist_ok=True)
            (path / "fixture.txt").write_bytes(b"first-party helper source")
        for name, revision in (("syncplay", "a" * 40), ("fastjsonschema", "b" * 40)):
            with (self.root / ".gitmodules").open("a") as stream:
                stream.write(f'[submodule "{name}"]\n path = 3rdparty/{name}\n url = https://example.invalid/{name}.git\n')
            (self.root / "3rdparty" / name).mkdir(parents=True, exist_ok=True)
        self.git("add", ".")
        for name, revision in (("syncplay", "a" * 40), ("fastjsonschema", "b" * 40)):
            self.git("update-index", "--add", "--cacheinfo", "160000", revision, "3rdparty/" + name)
        self.git("commit", "-qm", "Native helper inputs")
        payload = self.root / "artifacts/helper-payload"
        (payload / "bin").mkdir(parents=True); (payload / "app").mkdir()
        executable = "bin/syncwatch-helper" + (".exe" if TARGET == "windows-x64" else "")
        (payload / executable).write_bytes(b"native helper fixture")
        (payload / "app/syncplay-revision.txt").write_text("a" * 40 + "\n")
        self.helper_receipt = {"schemaVersion": 1, "target": TARGET, "developmentHelperOnly": True,
            "authenticatedInstallation": False, "sourceCommit": self.git("rev-parse", "HEAD"),
            "sourceTree": self.git("rev-parse", "HEAD^{tree}"), "localChanges": False,
            "firstPartyInputs": ci_inputs.first_party_inputs(self.root), "syncplayRevision": "a" * 40,
            "validatorRevision": "b" * 40,
            "files": {path.relative_to(payload).as_posix(): D.digest(path) for path in payload.rglob("*") if path.is_file()}}
        receipt_path = payload / "helper-report.json"
        receipt_path.write_text(json.dumps(self.helper_receipt))
        self.helper_acceptance = {"sourceCommit": self.helper_receipt["sourceCommit"], "target": TARGET,
            "helperReceiptSha256": D.digest(receipt_path),
            "session": {name: True for name in ("coalescedFrames", "identicalReplay", "shutdown", "oversizedInputClosed")}}
        acceptance = self.root / "artifacts/acceptance.json"; acceptance.write_text(json.dumps(self.helper_acceptance))
        log = self.root / "artifacts/native.log"; log.write_bytes(b"SYNCWATCH_NATIVE_BRIDGE_OK\n")
        self.origin = self.root / "artifacts/origin.json"
        write_origin(self.helper_receipt, self.origin, run_id="12", run_attempt="1")
        self.helper_archive = self.root / "artifacts/helper.zip"
        write_archive(payload, [("origin.json", self.origin), ("acceptance.json", acceptance), ("native-probe.log", log)], self.helper_archive)

    def import_helper(self):
        return ci_inputs.import_helper(self.helper_archive, self.output, target=TARGET,
                                       run_id=12, producer_attempt=1, root=self.root)

    def rewrite_helper(self, changes):
        with zipfile.ZipFile(self.helper_archive) as package:
            entries = {item.filename: package.read(item) for item in package.infolist()}
        entries.update(changes)
        with zipfile.ZipFile(self.helper_archive, "w") as package:
            for name, value in entries.items(): package.writestr(name, value)

    def test_native_helper_import_uses_producer_receipt_and_keeps_validation_outside_runtime(self):
        self.helper_fixture(); payload = self.import_helper()
        self.assertEqual(ci_inputs.checked_receipt(payload, "helper-report.json"), self.helper_receipt)
        self.assertTrue((self.output / "origin.json").is_file())
        self.assertTrue((self.output / "acceptance.json").is_file())
        self.assertFalse((payload / "native-probe.log").exists())
        self.assertFalse((payload / "acceptance.json").exists())
        self.assertFalse(any(path.name.startswith(".helper-import-") for path in self.output.iterdir()))

    def test_helper_wrong_run_source_target_and_failed_native_acceptance_fail_closed(self):
        self.helper_fixture()
        original = self.helper_archive.read_bytes()
        origin = json.loads(self.origin.read_text())
        for delta in ({"runId": "13"}, {"runAttempt": "2"}, {"sourceCommit": "f" * 40},
                      {"localChanges": True}, {"target": "wrong-os"}):
            self.helper_archive.write_bytes(original)
            self.rewrite_helper({"origin.json": json.dumps(origin | delta).encode()})
            with self.assertRaises(ValueError): self.import_helper()
            self.assertFalse(self.output.exists())
        self.helper_archive.write_bytes(original)
        self.rewrite_helper({"native-probe.log": b"failed native fixture"})
        with self.assertRaisesRegex(ValueError, "native acceptance"): self.import_helper()
        self.assertFalse(self.output.exists())

    def test_helper_source_mutation_corruption_and_unexpected_members_leave_no_output(self):
        self.helper_fixture(); original = self.helper_archive.read_bytes()
        source = self.root / "packages/syncplay-helper/fixture.txt"; data = source.read_bytes(); source.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "first-party inputs"): self.import_helper()
        source.write_bytes(data)
        for change in ({"payload/app/syncplay-revision.txt": b"corrupt"}, {"../escaped": b"escape"}):
            self.helper_archive.write_bytes(original); self.rewrite_helper(change)
            with self.assertRaises(ValueError): self.import_helper()
            self.assertFalse(self.output.exists())

    def test_helper_existing_output_is_preserved_and_interrupted_extraction_is_cleaned(self):
        self.helper_fixture(); self.output.mkdir(); (self.output / "user.txt").write_bytes(b"preserve")
        with self.assertRaises(FileExistsError): self.import_helper()
        self.assertEqual((self.output / "user.txt").read_bytes(), b"preserve")
        shutil.rmtree(self.output)
        with patch.object(D, "extract_payload", side_effect=OSError("interrupted helper copy")):
            with self.assertRaises(OSError): self.import_helper()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
