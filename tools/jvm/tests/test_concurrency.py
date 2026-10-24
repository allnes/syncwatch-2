"""Cache verification must retain exact binaries, source correspondence and grants."""

import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import concurrency
from build_support import digest, jar_bytes


class ConcurrencyCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.payload = Path(temporary.name)
        self.files = {"fixture": {"LICENSE": b"Original fixture grant\n", "source.kt": b"// Original fixture\n"}}
        self.profile = {"sources": {"fixture": {"revision": "0" * 40, "notices": ["LICENSE"], "license": "Apache-2.0"}}}
        self.notices = {"notices/fixture/LICENSE": self.files["fixture"]["LICENSE"]}
        entries = {"META-INF/UPSTREAM-NOTICES.txt": b"Original notices", "META-INF/CHANGES.txt": b"Build profile",
                   "META-INF/versions/9/module-info.class": b"Fixture only, never executed"}
        pins = {}
        for name in [*concurrency.BINARIES.values(), "compile-annotations.jar"]:
            data = jar_bytes(entries)
            (self.payload / name).write_bytes(data)
            pins[name] = digest(data)
        self.profile["expectedJars"] = {concurrency.jdk.current_target(): pins}
        self.sources = self.payload / "concurrency-sources.jar"
        self.sources.write_bytes(jar_bytes(concurrency.support(self.files, self.profile)))
        for name, data in self.notices.items():
            path = self.payload / name
            path.parent.mkdir(parents=True)
            path.write_bytes(data)

    def check_payload(self):
        concurrency.verify(self.payload, self.files, self.profile, self.notices)

    def test_notice_removal_change_or_unexpected_file_fails(self):
        self.check_payload()
        path = self.payload / next(iter(self.notices))
        path.write_bytes(b"Replacement grant")
        with self.assertRaisesRegex(ValueError, "notice changed"):
            self.check_payload()
        path.unlink()
        with self.assertRaisesRegex(ValueError, "missing or unexpected"):
            self.check_payload()

    def test_mutated_binary_and_original_source_correspondence_fail(self):
        binary = self.payload / next(iter(concurrency.BINARIES.values()))
        original = binary.read_bytes()
        binary.write_bytes(original + b"changed")
        with self.assertRaisesRegex(ValueError, "compiler output"):
            self.check_payload()
        binary.write_bytes(original)
        changed = copy.deepcopy(self.files)
        changed["fixture"]["source.kt"] += b"changed"
        self.sources.write_bytes(jar_bytes(concurrency.support(changed, self.profile)))
        with self.assertRaisesRegex(ValueError, "original sources"):
            self.check_payload()

    def test_extra_binary_or_missing_target_pin_fails(self):
        extra = self.payload / "registry-runtime.jar"
        extra.write_bytes(b"Unexpected library")
        with self.assertRaisesRegex(ValueError, "missing or unexpected"):
            self.check_payload()
        extra.unlink()
        self.profile["expectedJars"][concurrency.jdk.current_target()].pop("compile-annotations.jar")
        self.sources.write_bytes(jar_bytes(concurrency.support(self.files, self.profile)))
        with self.assertRaisesRegex(ValueError, "annotation pins"):
            self.check_payload()


if __name__ == "__main__":
    unittest.main()
