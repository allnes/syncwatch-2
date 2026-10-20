import copy
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sdk_probe
import source_analysis
import startup_sources as sources


class StartupSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = sources.profile_data()
        target = {("Darwin", "arm64"): "macos-arm64", ("Linux", "x86_64"): "linux-x64",
                  ("Windows", "AMD64"): "windows-x64"}[(platform.system(), platform.machine())]
        cls.files = sources.read_snapshot(sources.ROOT / "artifacts/dependencies" / sources.COMPONENT / target / "cpython.tar",
                                          cls.profile["source"])
        cls.expected = sources.payload_files(cls.files, cls.profile)

    def test_actual_developer_sdk_ignores_controlled_poison_and_handles_unicode(self):
        report = sdk_probe.probe()
        self.assertTrue(report["developerSdkOnly"])
        self.assertTrue(all(value is True for value in report["cases"].values()))
        for key in ("nativeRuntimeBuilt", "embeddingAbiVerified", "runtimeReady"):
            self.assertIs(report[key], False)

    def test_changed_field_type_is_rejected(self):
        files = self.files.copy()
        files["Include/cpython/initconfig.h"] = files["Include/cpython/initconfig.h"].replace(b"int safe_path;", b"long safe_path;")
        with self.assertRaisesRegex(ValueError, "startup field"):
            source_analysis.analyze(files, self.profile)

    def test_duplicate_field_is_rejected(self):
        files = self.files.copy()
        files["Include/cpython/initconfig.h"] = files["Include/cpython/initconfig.h"].replace(b"int safe_path;", b"int safe_path; int safe_path;")
        with self.assertRaisesRegex(ValueError, "startup field"):
            source_analysis.analyze(files, self.profile)

    def test_function_in_comment_does_not_replace_a_declaration(self):
        files = self.files.copy()
        declaration = b"PyAPI_FUNC(void) PyConfig_Clear(PyConfig *);"
        files["Include/cpython/initconfig.h"] = files["Include/cpython/initconfig.h"].replace(declaration, b"/* " + declaration + b" */")
        with self.assertRaisesRegex(ValueError, "startup function"):
            source_analysis.analyze(files, self.profile)

    def test_duplicate_function_is_rejected(self):
        files = self.files.copy()
        files["Include/pylifecycle.h"] += b"\nPyAPI_FUNC(int) Py_FinalizeEx(void);\n"
        with self.assertRaisesRegex(ValueError, "startup function"):
            source_analysis.analyze(files, self.profile)

    def test_changed_function_signature_is_rejected(self):
        files = self.files.copy()
        files["Include/pylifecycle.h"] = files["Include/pylifecycle.h"].replace(b"PyAPI_FUNC(int) Py_FinalizeEx(void);",
                                                                             b"PyAPI_FUNC(void) Py_FinalizeEx(void);")
        with self.assertRaisesRegex(ValueError, "startup function"):
            source_analysis.analyze(files, self.profile)

    def test_different_interpreter_version_is_rejected(self):
        profile = copy.deepcopy(self.profile)
        profile["version"] = "0.0.0"
        with self.assertRaisesRegex(ValueError, "version declaration"):
            source_analysis.analyze(self.files, profile)

    def test_policy_cannot_enable_environment_or_argument_parsing(self):
        for structure, field in [("preConfig", "use_environment"), ("config", "parse_argv")]:
            profile = copy.deepcopy(self.profile)
            profile["startupPolicy"][structure][field] = 1
            with self.subTest(structure=structure, field=field), self.assertRaisesRegex(ValueError, "isolate"):
                source_analysis.analyze(self.files, profile)

    def test_false_unknown_and_non_boolean_sdk_results_are_rejected(self):
        good = {name: True for name in sdk_probe.CASES}
        bad = [good | {"noSite": False}, good | {"noSite": 1}, good | {"unexpected": True},
               {name: value for name, value in good.items() if name != "noSite"}]
        for result in bad:
            with self.subTest(result=result), self.assertRaisesRegex(ValueError, "checks failed"):
                sdk_probe.validate(json.dumps(result))
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            sdk_probe.validate(b"not JSON")

    def test_sdk_timeout_fails_without_publishing_child_diagnostics(self):
        with patch.object(sdk_probe.subprocess, "run", side_effect=subprocess.TimeoutExpired("controlled", 30)):
            with self.assertRaisesRegex(ValueError, "timed out"):
                sdk_probe.probe()

    def test_sdk_output_limit_is_enforced(self):
        def oversized(*args, **kwargs):
            kwargs["stdout"].write(b"x" * 4097)
            return SimpleNamespace(returncode=0)
        with patch.object(sdk_probe.subprocess, "run", side_effect=oversized):
            with self.assertRaisesRegex(ValueError, "output limit"):
                sdk_probe.probe()

    def test_original_source_and_notice_digest_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, data in self.files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            for name in ("LICENSE", "Include/cpython/initconfig.h"):
                path = root / name
                path.write_bytes(self.files[name] + b"\nchanged\n")
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "digest changed"):
                    sources.read_snapshot(root, self.profile["source"])
                path.write_bytes(self.files[name])

    def test_missing_and_altered_full_notices_or_selection_summary_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, data in self.expected.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            sources.verify(root, self.expected)
            for name in ("notices/cpython/LICENSE", "notices/cpython/README.rst", "SELECTION.txt"):
                path = root / name
                path.write_bytes(b"shortened")
                with self.subTest(name=name, mutation="altered"), self.assertRaisesRegex(ValueError, "differs"):
                    sources.verify(root, self.expected)
                path.unlink()
                with self.subTest(name=name, mutation="missing"), self.assertRaisesRegex(ValueError, "missing"):
                    sources.verify(root, self.expected)
                path.write_bytes(self.expected[name])
            (root / "unreviewed-library.dll").write_bytes(b"not allowed")
            with self.assertRaisesRegex(ValueError, "differs"):
                sources.verify(root, self.expected)

    def test_packaging_cannot_enable_the_unresolved_runtime(self):
        original = sources.json.loads
        def changed(data):
            value = original(data)
            if "components" in value:
                value["components"]["syncplay-runtime"]["status"] = "ready"
            return value
        with patch.object(sources.json, "loads", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "non-executable"):
                sources.profile_data()


if __name__ == "__main__":
    unittest.main()
