import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from helper_archive import write_archive


class ArchiveTests(unittest.TestCase):
    def test_old_cache_dates_and_host_permissions_do_not_change_artifact_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = root / "payload"
            (payload / "bin").mkdir(parents=True)
            binary = payload / "bin/syncwatch-helper"
            binary.write_bytes(b"controlled native fixture")
            data = payload / "unicode-\u03bc.txt"
            data.write_bytes(b"original source bytes\n")
            log = root / "native.log"
            log.write_bytes(b"accepted\n")
            for path in (binary, data, log):
                os.utime(path, (0, 0))
            first, second = root / "first.zip", root / "second.zip"
            write_archive(payload, [("native-probe.log", log)], first)
            for path in (binary, data, log):
                os.utime(path, (1700000000, 1700000000))
            write_archive(payload, [("native-probe.log", log)], second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), sorted(archive.namelist()))
                for entry in archive.infolist():
                    self.assertEqual(entry.date_time, (1980, 1, 1, 0, 0, 0))
                    self.assertEqual(entry.create_system, 3)
                self.assertEqual(archive.read("payload/unicode-\u03bc.txt"), data.read_bytes())
                self.assertEqual(archive.getinfo("payload/bin/syncwatch-helper").external_attr >> 16, 0o100755)
                self.assertEqual(archive.getinfo("payload/unicode-\u03bc.txt").external_attr >> 16, 0o100644)


if __name__ == "__main__":
    unittest.main()
