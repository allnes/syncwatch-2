import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from receipts import checked_receipt


class RuntimeReceiptTests(unittest.TestCase):
    def fixture(self, root):
        (root / "runtime").write_bytes(b"pinned runtime")
        report = {"schemaVersion": 1, "files": {"runtime": hashlib.sha256(b"pinned runtime").hexdigest()}}
        (root / "receipt.json").write_text(json.dumps(report))
        return report

    def test_exact_inventory_is_required_after_relocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "build"
            root.mkdir()
            expected = self.fixture(root)
            relocated = root.parent / "Кино 映画 with spaces"
            root.rename(relocated)
            self.assertEqual(checked_receipt(relocated, "receipt.json"), expected)

    def test_modified_missing_and_unlisted_runtime_files_are_rejected(self):
        for mutation in ("changed", "missing", "extra", "malformed"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                report = self.fixture(root)
                if mutation == "changed":
                    (root / "runtime").write_bytes(b"modified")
                elif mutation == "missing":
                    (root / "runtime").unlink()
                elif mutation == "extra":
                    (root / "injected.dll").write_bytes(b"injected")
                else:
                    report["files"]["runtime"] = {"sha256": "unexpected object"}
                    (root / "receipt.json").write_text(json.dumps(report))
                with self.assertRaises(ValueError):
                    checked_receipt(root, "receipt.json")
