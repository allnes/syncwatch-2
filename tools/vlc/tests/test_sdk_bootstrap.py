"""Exercise the SDK archive boundary without an ambient compression executable."""

import io
import os
from pathlib import Path
import sys
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import provision_sdks


class SdkBootstrapTests(unittest.TestCase):
    def test_linux_metadata_refresh_is_bounded_before_package_installation(self):
        with patch.object(provision_sdks.platform, "system", return_value="Linux"), patch.object(provision_sdks.subprocess, "run") as run:
            provision_sdks.main()
        refresh, install = run.call_args_list
        command = refresh.args[0]
        self.assertEqual(command[:3], ["sudo", "-n", "timeout"])
        self.assertIn("--kill-after=10s", command)
        self.assertIn("300s", command)
        self.assertLessEqual(refresh.kwargs["timeout"], 330)
        self.assertIn("update", command)
        self.assertIn("install", install.args[0])
        # Downloads remain bounded; installing/configuring packages is not forcibly cut short.
        for call in (refresh, install):
            self.assertIn("Acquire::http::Timeout=30", call.args[0])
            self.assertIn("Acquire::https::Timeout=30", call.args[0])
            self.assertTrue(call.kwargs["check"])
        self.assertNotIn("timeout", install.args[0])

    def test_failed_or_timed_out_refresh_cannot_install_from_stale_metadata(self):
        for failure in (subprocess.CalledProcessError(124, "apt-refresh"), subprocess.TimeoutExpired("apt-refresh", 330)):
            with self.subTest(failure=type(failure).__name__), patch.object(provision_sdks.platform, "system", return_value="Linux"), patch.object(provision_sdks.subprocess, "run", side_effect=failure) as run:
                with self.assertRaises(type(failure)):
                    provision_sdks.main()
                run.assert_called_once()

    def archive(self, directory, name):
        path = directory / "base.tar.xz"
        with tarfile.open(path, "w:xz") as archive:
            entry = tarfile.TarInfo(name)
            entry.size = 4
            archive.addfile(entry, io.BytesIO(b"test"))
        return path

    def test_xz_is_decoded_before_invoking_the_declared_bootstrap_tar(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            archive = self.archive(directory, "msys64/usr/bin/bash.exe")
            def extract(command, **kwargs):
                uncompressed = Path(command[command.index("-xf") + 1])
                self.assertEqual(uncompressed.suffix, ".tar")
                with tarfile.open(uncompressed, "r:") as source:
                    self.assertEqual(source.extractfile(source.getmembers()[0]).read(), b"test")
            with patch.dict(os.environ, {"PATH": ""}), patch.object(provision_sdks.subprocess, "run", side_effect=extract) as run:
                provision_sdks.unpack_windows_base(archive, directory)
            run.assert_called_once()
            self.assertEqual(sorted(p.name for p in directory.iterdir()), ["base.tar.xz"])

    def test_foreign_archive_path_is_rejected_before_bootstrap_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            archive = self.archive(directory, "../foreign")
            with patch.object(provision_sdks.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    provision_sdks.unpack_windows_base(archive, directory)
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
