"""Compile preparation must work without a developer's initialized source checkout."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ci


class CleanCheckoutHeadersTests(unittest.TestCase):
    def test_native_packaging_initializes_pinned_headers_before_compiling_the_bridge(self):
        for target in ("windows-x64", "linux-x64"):
            with self.subTest(target=target):
                self.check_target(target)

    def check_target(self, target):
        with tempfile.TemporaryDirectory(prefix="sw-ci-headers-") as temporary:
            base = Path(temporary)
            source, root = base / "upstream", base / "consumer"
            for directory in (source, root):
                directory.mkdir()
                self.git(directory, "init", "-q")
            header = source / "include/vlc/libvlc.h"
            header.parent.mkdir(parents=True)
            header.write_text("/* pinned header fixture */\n")
            self.git(source, "add", ".")
            self.commit(source)
            pin = self.git(source, "rev-parse", "HEAD")
            header.write_text("/* newer header must not be selected */\n")
            self.git(source, "add", ".")
            self.commit(source)
            (root / ".gitmodules").write_text('[submodule "vlc"]\npath = 3rdparty/vlc\nurl = ' + source.as_posix() + '\n')
            (root / ".gitignore").write_text("artifacts/\n")
            self.git(root, "add", ".gitmodules", ".gitignore")
            self.git(root, "update-index", "--add", "--cacheinfo", "160000," + pin + ",3rdparty/vlc")
            self.commit(root)
            public_header = root / "3rdparty/vlc/include/vlc/libvlc.h"
            self.assertFalse(public_header.exists())
            original_run = ci.run
            compiled = []
            def run(*command):
                if command[0] == "git":
                    original_run(*command)
                elif "tools/playback/build.py" in command:
                    self.assertEqual(public_header.read_text(), "/* pinned header fixture */\n")
                    self.assertEqual(self.git(root / "3rdparty/vlc", "rev-parse", "HEAD"), pin)
                    compiled.append(True)
            # All compiler/SDK work is mocked; only source provisioning uses a
            # real Git submodule, so this common Python test runs on all hosts.
            with patch.object(ci, "ROOT", root), patch.object(ci, "require_host"), \
                    patch.object(ci, "restore", return_value=base), patch.object(ci, "linux_inputs", return_value=base), \
                    patch.object(ci, "run", side_effect=run), \
                    patch.dict(os.environ, {"GIT_ALLOW_PROTOCOL": "file"}):
                ci.build(target, dotnet=base / "fixture-dotnet")
            self.assertEqual(compiled, [True])
            self.assertEqual(self.git(root, "status", "--porcelain"), "")

    @staticmethod
    def git(directory, *command):
        return subprocess.check_output(["git", *command], cwd=directory, text=True, stderr=subprocess.DEVNULL).strip()

    def commit(self, directory):
        self.git(directory, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Fixture")
