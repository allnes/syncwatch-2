from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ci
import linux_probe


class NativeHostTests(unittest.TestCase):
    def test_foreign_client_options_fail_before_runtime_build(self):
        for target in ("macos-arm64", "linux-x64"):
            with self.subTest(target=target), patch.object(ci, "target", return_value=target), patch.object(ci, "check") as build:
                with self.assertRaisesRegex(ValueError, "C#.*only on Windows"):
                    ci.verify(dotnet="foreign-client")
                build.assert_not_called()
        for target in ("macos-arm64", "windows-x64"):
            with self.subTest(target=target), patch.object(ci, "target", return_value=target), patch.object(ci, "check") as build:
                with self.assertRaisesRegex(ValueError, "Kotlin.*only used on Linux"):
                    ci.verify(kotlin_runtime=Path("foreign-client"))
                build.assert_not_called()

    def test_linux_provisions_jvm_tools_without_dotnet(self):
        with patch.object(ci, "target", return_value="linux-x64"), patch.object(ci.subprocess, "run") as run:
            ci.provision()
        tools = [Path(call.args[0][1]).name for call in run.call_args_list[1:]]
        self.assertEqual(tools, ["jdk.py", "kotlin.py", "build.py"])
        self.assertIn("kotlin-stdlib", run.call_args_list[-1].args[0])

    def test_explicit_owned_runtime_reuses_artifact_before_probe_verification(self):
        with patch.object(ci, "target", return_value="linux-x64"), patch.object(ci.subprocess, "run") as run:
            ci.provision(Path("owned-stdlib-artifact"))
        self.assertEqual(len(run.call_args_list), 3)

    def test_kotlin_probe_rejects_foreign_host_before_loading_client(self):
        for target in ("darwin", "win32"):
            with self.subTest(target=target), patch.object(linux_probe.sys, "platform", target):
                with self.assertRaisesRegex(ValueError, "requires Linux"):
                    linux_probe.check(Path("helper"), Path("runtime"))


if __name__ == "__main__":
    unittest.main()
