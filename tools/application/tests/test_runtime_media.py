"""A codec-only update must neither rebuild the JVM nor silently change its linkage."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from receipts import checked_receipt
from runtime_media import qualify


class RuntimeMediaTests(unittest.TestCase):
    def fixture(self, path, *, plugin=b"old decoder", changed=None):
        files = {"include/X11/Xlib.h": b"pinned headers", "lib/libX11.so.6": b"pinned library",
                 "share/fonts/fonts.conf": b"pinned configuration", "lib/vlc/plugins/selected/codec.so": plugin}
        files.update(changed or {})
        for name, data in files.items():
            member = path / name
            member.parent.mkdir(parents=True, exist_ok=True)
            member.write_bytes(data)
        receipt = {"schemaVersion": 1, "sources": {"vlc": {"revision": "pinned"}},
                   "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
        (path / "build-report.json").write_text(json.dumps(receipt))
        return {"mediaReceiptSha256": hashlib.sha256((path / "build-report.json").read_bytes()).hexdigest()}

    def admission(self, package, target):
        self.assertEqual(target, "linux-x64")
        return checked_receipt(package, "build-report.json")

    def test_same_receipt_needs_no_compatibility_or_original_package(self):
        with tempfile.TemporaryDirectory() as temporary, patch("runtime_media.media", self.admission):
            root = Path(temporary)
            runtime = self.fixture(root)
            self.assertIsNone(qualify(root, None, runtime, runtime))

    def test_only_plugin_changes_preserve_original_receipt_and_exact_linkage(self):
        with tempfile.TemporaryDirectory() as temporary, patch("runtime_media.media", self.admission):
            root = Path(temporary)
            old, new = root / "old", root / "new"
            runtime = self.fixture(old)
            self.fixture(new, plugin=b"new decoder")
            result = qualify(new, old, runtime, runtime)
            self.assertEqual(result.build_receipt, (old / "build-report.json").read_bytes())
            self.assertEqual(result.report["originalMediaReceiptSha256"], runtime["mediaReceiptSha256"])
            self.assertEqual(len(result.report["linkageInputsUnchanged"]), 3)

    def test_changed_native_inputs_require_rebuilding_even_with_valid_receipts(self):
        for name in ("include/X11/Xlib.h", "lib/libX11.so.6", "share/fonts/fonts.conf", "lib/added.so"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary, patch("runtime_media.media", self.admission):
                root = Path(temporary)
                runtime = self.fixture(root / "old")
                self.fixture(root / "new", changed={name: b"changed"})
                with self.assertRaisesRegex(ValueError, "rebuild"):
                    qualify(root / "new", root / "old", runtime, runtime)

    def test_missing_or_unrelated_original_package_and_mixed_runtimes_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, patch("runtime_media.media", self.admission):
            root = Path(temporary)
            runtime = self.fixture(root / "old")
            other = self.fixture(root / "new", plugin=b"new decoder")
            for original, clients in ((None, runtime), (root / "new", runtime), (root / "old", other)):
                with self.subTest(original=original, clients=clients), self.assertRaises(ValueError):
                    qualify(root / "new", original, runtime, clients)

    def test_tampered_or_missing_runtime_members_are_rejected(self):
        for deleted in (False, True):
            with self.subTest(deleted=deleted), tempfile.TemporaryDirectory() as temporary, patch("runtime_media.media", self.admission):
                root = Path(temporary)
                runtime = self.fixture(root / "old")
                self.fixture(root / "new", plugin=b"new decoder")
                member = root / "old/lib/libX11.so.6"
                if deleted:
                    member.unlink()
                else:
                    member.write_bytes(b"tampered")
                with self.assertRaises(ValueError):
                    qualify(root / "new", root / "old", runtime, runtime)
