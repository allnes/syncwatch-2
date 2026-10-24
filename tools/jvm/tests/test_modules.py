"""Source-set ownership errors must fail before a compiler can accept a false graph."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modules import fragment_arguments


class FragmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sources = {}
        for name in ("common", "concurrent", "jvm"):
            path = self.root / (name + ".kt")
            path.write_text("// Original source fixture\n")
            self.sources[name] = [path]

    def test_intermediate_actuals_retain_their_refinement(self):
        arguments, sources = fragment_arguments(self.sources, [("jvm", "concurrent"), ("concurrent", "common")])
        self.assertIn("-Xfragment-refines=concurrent:common", arguments)
        self.assertIn("-Xfragment-refines=jvm:concurrent", arguments)
        self.assertIn("-Xfragment-sources=concurrent:" + str(self.sources["concurrent"][0].resolve()), arguments)
        self.assertNotIn("-Xcommon-sources", " ".join(arguments))
        self.assertEqual(len(sources), 3)

    def test_cycles_disconnected_leaves_unknown_parents_and_duplicate_edges_fail(self):
        for edges in [[("jvm", "concurrent"), ("concurrent", "jvm")], [], [("jvm", "unknown")],
                      [("jvm", "common"), ("jvm", "common")]]:
            with self.subTest(edges=edges), self.assertRaises(ValueError):
                fragment_arguments(self.sources, edges)

    def test_shared_or_missing_source_is_rejected(self):
        edges = [("jvm", "concurrent"), ("concurrent", "common")]
        self.sources["concurrent"] = self.sources["common"]
        with self.assertRaisesRegex(ValueError, "multiple"):
            fragment_arguments(self.sources, edges)
        self.sources["concurrent"] = [self.root / "missing.kt"]
        with self.assertRaisesRegex(ValueError, "existing"):
            fragment_arguments(self.sources, edges)

    def test_common_only_library_requires_explicit_empty_platform_permission(self):
        sources = {"common": self.sources["common"], "jvm": []}
        with self.assertRaisesRegex(ValueError, "JVM leaf"):
            fragment_arguments(sources, [("jvm", "common")])
        flags, files = fragment_arguments(sources, [("jvm", "common")], allow_empty_platform=True)
        self.assertEqual(len(files), 1)
        self.assertIn("-Xfragment-refines=jvm:common", flags)
        with self.assertRaises(ValueError):
            fragment_arguments({"common": [], "jvm": []}, [("jvm", "common")], allow_empty_platform=True)

    def test_java_interop_sources_belong_only_to_the_platform_leaf(self):
        java = self.root / "Original.java"
        java.write_text("class Original {}\n")
        self.sources["jvm"].append(java)
        _, files = fragment_arguments(self.sources, [("jvm", "concurrent"), ("concurrent", "common")])
        self.assertIn(str(java.resolve()), files)
        self.sources["jvm"].remove(java)
        self.sources["common"].append(java)
        with self.assertRaisesRegex(ValueError, "JVM-leaf"):
            fragment_arguments(self.sources, [("jvm", "concurrent"), ("concurrent", "common")])


if __name__ == "__main__":
    unittest.main()
