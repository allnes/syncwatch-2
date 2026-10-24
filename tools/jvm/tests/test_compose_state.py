"""Cache reuse preserves the exact runtime, original sources and legal inputs."""

import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compose_state
from build_support import digest, jar_bytes


class ComposeStateCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.payload = Path(temporary.name)
        self.files = {"fixture": {"LICENSE": b"Original fixture grant", "source.kt": b"// Original fixture"}}
        self.profile = {"sources": {"fixture": {}}, "modules": [{"binary": "runtime.jar"}],
                        "expectedJars": {compose_state.jdk.current_target(): {"runtime.jar": digest(b"Fixture bytecode")}}}
        self.notices = {"notices/fixture/LICENSE": self.files["fixture"]["LICENSE"]}
        (self.payload / "runtime.jar").write_bytes(b"Fixture bytecode")
        (self.payload / "compose-state-sources.jar").write_bytes(jar_bytes(compose_state.support(self.files, self.profile)))
        for name, data in self.notices.items():
            path = self.payload / name
            path.parent.mkdir(parents=True)
            path.write_bytes(data)

    def verify(self):
        compose_state.verify(self.payload, self.files, self.profile, self.notices)

    def test_modified_or_missing_original_notice_and_extra_runtime_fail(self):
        self.verify()
        path = self.payload / next(iter(self.notices))
        path.write_bytes(b"Replacement notice")
        with self.assertRaisesRegex(ValueError, "notice changed"):
            self.verify()
        path.write_bytes(next(iter(self.notices.values())))
        extra = self.payload / "registry-library.jar"
        extra.write_bytes(b"Unreviewed runtime")
        with self.assertRaisesRegex(ValueError, "unexpected files"):
            self.verify()
        extra.unlink()
        path.unlink()
        with self.assertRaisesRegex(ValueError, "missing or unexpected"):
            self.verify()

    def test_binary_source_and_compiler_profile_tampering_fail(self):
        (self.payload / "runtime.jar").write_bytes(b"Modified binary")
        with self.assertRaisesRegex(ValueError, "compiler output"):
            self.verify()
        (self.payload / "runtime.jar").write_bytes(b"Fixture bytecode")
        for change in ("source", "profile"):
            files, profile = copy.deepcopy(self.files), copy.deepcopy(self.profile)
            if change == "source":
                files["fixture"]["source.kt"] += b"modified"
            else:
                profile["compilerVersion"] = "Unreviewed compiler"
            (self.payload / "compose-state-sources.jar").write_bytes(jar_bytes(compose_state.support(files, profile)))
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "original sources, notices or profile"):
                self.verify()

    def test_every_runtime_requires_a_target_pin(self):
        self.profile["expectedJars"][compose_state.jdk.current_target()].clear()
        (self.payload / "compose-state-sources.jar").write_bytes(jar_bytes(compose_state.support(self.files, self.profile)))
        with self.assertRaisesRegex(ValueError, "every runtime artifact"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
