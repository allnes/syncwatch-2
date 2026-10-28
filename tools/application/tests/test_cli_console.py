"""Publishing a valid package must not fail when its status reaches a legacy Windows console."""

import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import package as package_cli
from candidate_tree import Component, inventory

TARGET = {"darwin": "macos-arm64", "win32": "windows-x64", "linux": "linux-x64"}[sys.platform]


class CandidateConsoleTests(unittest.TestCase):
    def test_unicode_package_publishes_and_reports_success_in_cp1252(self):
        with tempfile.TemporaryDirectory(prefix="sw-cli-console-") as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            application = source / "application"
            application.write_bytes(b"owned authored fixture")
            output = root / "Кино 映画 with spaces"
            arguments = ["package.py", "--target", TARGET, "--application", str(application),
                         "--media-package", str(source), "--helper-package", str(source), "--output", str(output)]
            for option in ("bridge", "dotnet", "jvm", "desktop-sdk", "renderer", "linux-clients"):
                arguments += ["--" + option, str(source)]
            inputs = {"commit": "a" * 40, "localChanges": False, "files": {}}
            # Stub native producers and SDK admission only. The actual candidate transaction,
            # inventory, receipt and final CLI output run against the filesystem and CP1252 stream.
            adapter = SimpleNamespace(prepare=lambda *_: [Component(source, "SyncWatch")])
            data = io.BytesIO()
            console = io.TextIOWrapper(data, encoding="cp1252", errors="strict", write_through=True)
            with (patch.object(sys, "argv", arguments), patch.object(sys, "stdout", console),
                  patch.object(package_cli, "media"), patch.object(package_cli, "helper"),
                  patch.object(package_cli, "source_inputs", return_value=inputs),
                  patch.object(package_cli, "importlib", SimpleNamespace(import_module=lambda _: adapter))):
                package_cli.main()
            receipt = json.loads((output / "candidate.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["files"], inventory(output / "contents"))
            self.assertEqual((output / "contents/SyncWatch/application").read_bytes(), application.read_bytes())
            self.assertGreater(len(data.getvalue().decode("cp1252")), 0)
            console.close()


if __name__ == "__main__":
    unittest.main()
