import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from receipts import source_inputs


class SourceInputTests(unittest.TestCase):
    def test_dirty_overlay_cannot_be_presented_as_the_unchanged_git_base(self):
        with tempfile.TemporaryDirectory(prefix="sw-source-inputs-") as temporary:
            root = Path(temporary)
            environment = os.environ | {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"}
            def git(*arguments):
                subprocess.run(["git", *arguments], cwd=root, env=environment, check=True, capture_output=True)
            for name in ("apps", "packages", "contracts", "tools"):
                (root / name).mkdir()
                (root / name / "source.txt").write_text("original")
            for name in ("global.json", "LICENSE", ".gitmodules"):
                (root / name).write_text("original")
            (root / ".gitmodules").write_text("")
            git("init", "--quiet")
            git("add", ".")
            git("-c", "user.name=SyncWatch Test", "-c", "user.email=syncwatch@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "baseline")
            before = source_inputs(root)
            self.assertFalse(before["localChanges"])
            (root / "apps/source.txt").write_text("overlay")
            (root / "packages/new-source.txt").write_text("new untracked input")
            after = source_inputs(root)
            self.assertEqual(before["commit"], after["commit"])
            self.assertTrue(after["localChanges"])
            self.assertNotEqual(before["files"]["apps/source.txt"], after["files"]["apps/source.txt"])
            self.assertIn("packages/new-source.txt", after["files"])
            self.assertNotIn(str(root), json.dumps(after))
