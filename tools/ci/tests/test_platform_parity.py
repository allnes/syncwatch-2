import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_platform_parity import LINUX_COMPONENTS, check

ROOT = Path(__file__).resolve().parents[3]


class PlatformParityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ("tools/native/platforms.json", ".github/workflows/repository.yml", "apps/linux/application.json", "tools/dependencies/components.json"):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        self.path = self.root / "tools/native/platforms.json"
        self.data = json.loads(self.path.read_text())
        for modules in self.data["platforms"].values():
            for directory in modules.values():
                path = self.root / directory
                path.mkdir(parents=True, exist_ok=True)
                (path / "Implementation.kt").write_text("class Implementation\n")

    def save(self):
        self.path.write_text(json.dumps(self.data) + "\n")

    def test_missing_linux_cannot_pass_as_two_clients(self):
        del self.data["platforms"]["linux"]
        self.save()
        with self.assertRaisesRegex(ValueError, "macos, windows and linux"):
            check(self.root)

    def test_empty_folder_is_not_an_implementation(self):
        (self.root / "apps/linux/Implementation.kt").unlink()
        with self.assertRaisesRegex(ValueError, "empty folder"):
            check(self.root)

    def test_source_or_boundary_results_cannot_complete_feature(self):
        for status in ("research-tested", "source-only", "native-boundary-tested", "missing"):
            self.data["featureSlices"]["shared-component-galleries"]["complete"] = True
            self.data["featureSlices"]["shared-component-galleries"]["validation"]["linux"] = status
            self.save()
            with self.assertRaisesRegex(ValueError, "cannot complete"):
                check(self.root)

    def test_every_feature_requires_three_explicit_states(self):
        del self.data["featureSlices"]["native-video-and-local-controls"]["validation"]["linux"]
        self.save()
        with self.assertRaisesRegex(ValueError, "three explicit"):
            check(self.root)

    def test_linux_ci_cannot_be_optional(self):
        path = self.root / ".github/workflows/repository.yml"
        workflow = json.loads(path.read_text())
        workflow["jobs"]["required"]["needs"].remove("linux")
        path.write_text(json.dumps(workflow))
        with self.assertRaisesRegex(ValueError, "required client CI"):
            check(self.root)

    def test_unknown_application_component_is_rejected(self):
        path = self.root / "apps/linux/application.json"
        application = json.loads(path.read_text())
        application["requiredSourceComponents"].append("invented-component")
        path.write_text(json.dumps(application))
        with self.assertRaisesRegex(ValueError, "registered source components"):
            check(self.root)

    def test_foreign_host_cannot_execute_linux_consumers(self):
        path = self.root / "tools/dependencies/components.json"
        original = json.loads(path.read_text())
        for name in LINUX_COMPONENTS:
            for target in ("macos-arm64", "windows-x64"):
                data = json.loads(json.dumps(original))
                data["components"][name]["targets"][target] = data["components"][name]["targets"]["linux-x64"]
                path.write_text(json.dumps(data))
                with self.subTest(component=name, target=target), self.assertRaisesRegex(ValueError, "only on Linux"):
                    check(self.root)

    def test_new_jvm_components_cannot_reintroduce_foreign_builds(self):
        path = self.root / "tools/dependencies/components.json"
        data = json.loads(path.read_text())
        data["components"]["future-jvm-api"] = {"targets": {
            "macos-arm64": {"toolchains": {"jdk": {}}},
        }}
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "only on Linux"):
            check(self.root)

    def test_unavailable_graph_cannot_claim_build_readiness(self):
        path = self.root / "apps/linux/application.json"
        application = json.loads(path.read_text())
        application["applicationBuildReady"] = True
        path.write_text(json.dumps(application))
        with self.assertRaisesRegex(ValueError, "Unavailable source components"):
            check(self.root)

    def test_apple_paths_do_not_replace_macos(self):
        (self.root / "apps/apple").mkdir()
        with self.assertRaisesRegex(ValueError, "Desktop implementation paths"):
            check(self.root)
