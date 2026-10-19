"""Regression checks for the boundary between declarative design and model bindings."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("design_isolation", ROOT / "tools/design/check_isolation.py")
isolation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isolation)


class DesignIsolationTests(unittest.TestCase):
    def fixture(self, platform, name, content):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for target in ("apple", "windows", "linux"):
            (root / "packages/design" / target).mkdir(parents=True)
        file = root / "packages/design" / platform / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)
        return root

    def test_native_screen_construction_is_rejected_on_each_platform(self):
        for platform, name, source in [
            ("apple", "AnotherScreen.swift", "HStack { Text(value) }.padding(2)"),
            ("windows", "AnotherScreen.cs", "var panel = new Grid(); panel.Width = 300;"),
            ("linux", "AnotherScreen.kt", "Row { BasicText(value) }.padding(2.dp)"),
        ]:
            with self.subTest(platform=platform):
                self.assertTrue(isolation.check(self.fixture(platform, name, source)))

    def test_observations_and_domain_numbers_remain_allowed(self):
        root = self.fixture("apple", "Bindings.swift", 'let positionMs = 1000; let view = DesignSurface("Player", context: model)')
        self.assertEqual(isolation.check(root), [])

    def test_trailing_closure_layout_without_modifiers_is_rejected(self):
        for platform, name, source in [
            ("apple", "Bindings.swift", 'HStack { DesignSurface("Player") }'),
            ("linux", "Bindings.kt", 'Row { DesignSurface("Player") }'),
        ]:
            with self.subTest(platform=platform):
                self.assertTrue(isolation.check(self.fixture(platform, name, source)))

    def test_component_subdirectories_cannot_bypass_isolation_or_impersonate_the_adapter(self):
        for platform, name, source in [
            ("apple", "selection/Bindings.swift", "HStack { Text(value) }.padding(2)"),
            ("windows", "selection/DesignSurface.cs", "var control = new Button();"),
            ("linux", "selection/DesignSurface.kt", "Row { BasicText(value) }.padding(2.dp)"),
        ]:
            with self.subTest(platform=platform):
                self.assertTrue(isolation.check(self.fixture(platform, name, source)))

    def test_primitive_construction_is_confined_to_the_mechanical_adapter(self):
        root = self.fixture("windows", "DesignSurface.cs", "var control = new Button();")
        self.assertEqual(isolation.check(root), [])
        (root / "packages/design/windows/ScreenHelper.cs").write_text("var control = new Button();")
        self.assertEqual(len(isolation.check(root)), 1)


if __name__ == "__main__":
    unittest.main()
