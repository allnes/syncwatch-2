"""Exercise the SDK archive boundary without an ambient compression executable."""

import io
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import provision_sdks


class SdkBootstrapTests(unittest.TestCase):
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
