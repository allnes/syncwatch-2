"""Reject modified runtime payloads before consumer code executes."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stdlib
from build_support import digest, jar_bytes


class StdlibTests(unittest.TestCase):
    def test_version_substitution_is_explicit_and_rejects_drift(self):
        original = b"/* original notice */ KotlinVersion(2, 3, 255) // upstream placeholder\n"
        self.assertEqual(stdlib.derivative(original), original.replace(b"255", b"20"))
        for invalid in [b"KotlinVersion(2, 3, 20)", original + original]:
            with self.assertRaisesRegex(ValueError, "reviewed version substitution"):
                stdlib.derivative(invalid)

    def test_cached_runtime_notices_profile_and_inventory_are_rechecked(self):
        with tempfile.TemporaryDirectory() as temporary:
            payload = Path(temporary)
            support = {n: ("Fixture " + n).encode() for n in
                       ["THIRD-PARTY-NOTICES.txt", "source-inventory.json", "unicode-provenance.json", "binary-profile.json", "CHANGES.txt"]}
            binary = jar_bytes({"META-INF/" + n: data for n, data in support.items()})
            expected = support | {stdlib.BINARY: binary, "annotations/" + stdlib.annotations.BINARY: b"annotations",
                                  "annotations/" + stdlib.annotations.SOURCES: b"original source"}
            (payload / "annotations").mkdir()
            for name, data in expected.items():
                (payload / name).write_bytes(data)
            profile = {"expectedJars": {target: {stdlib.BINARY: digest(binary)} for target in
                                      ("macos-arm64", "linux-x64", "windows-x64")}}
            def verify():
                stdlib.verify(payload, {}, {}, profile, {}, {"notices": []}, "fixture")
            with patch.object(stdlib, "support", return_value=support), patch.object(stdlib.annotations, "support_files", return_value={}), patch.object(stdlib.annotations, "verify") as annotation_verify:
                verify()
                annotation_verify.assert_called_once()
                for name in [*support, stdlib.BINARY]:
                    path = payload / name
                    with self.subTest(name=name):
                        path.write_bytes(expected[name] + b"changed")
                        with self.assertRaises(ValueError):
                            verify()
                        path.unlink()
                        with self.assertRaises(ValueError):
                            verify()
                        path.write_bytes(expected[name])
                (payload / "unexpected.jar").write_bytes(b"unregistered runtime")
                with self.assertRaisesRegex(ValueError, "unexpected files"):
                    verify()


if __name__ == "__main__":
    unittest.main()
