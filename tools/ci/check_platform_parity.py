"""Require three explicit client implementations and truthful feature completion declarations."""

import json
from pathlib import Path


PLATFORMS = {"macos", "windows", "linux"}
MODULES = {"application", "domain", "design", "generatedDesign", "playback", "bridge", "library"}
VALIDATION = {"native-tested", "native-boundary-tested", "research-tested", "source-only", "missing"}
LINUX_COMPONENTS = {"jvm-annotations", "kotlin-stdlib-sources", "kotlin-stdlib", "kotlinx-concurrency",
                    "compose-runtime", "compose-state", "compose-ui-jvm", "skiko-native-objects"}


def check(root: Path) -> None:
    manifest = json.loads((root / "tools/native/platforms.json").read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 1 or set(manifest.get("platforms", {})) != PLATFORMS:
        raise ValueError("Client platforms must be macos, windows and linux")
    for platform, modules in manifest["platforms"].items():
        if set(modules) != MODULES:
            raise ValueError(f"{platform}: missing client module")
        for name, relative in modules.items():
            path = root / relative
            if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink() or not path.is_dir():
                raise ValueError(f"{platform}/{name}: client implementation directory is missing")
            if not any(p.suffix in {".swift", ".cs", ".kt", ".java"} for p in path.rglob("*") if p.is_file()):
                raise ValueError(f"{platform}/{name}: an empty folder is not an implementation")
    if not manifest.get("featureSlices"):
        raise ValueError("Feature parity must be declared")
    for name, feature in manifest["featureSlices"].items():
        if set(feature) != {"complete", "validation"} or type(feature["complete"]) is not bool:
            raise ValueError(f"{name}: invalid feature declaration")
        if set(feature["validation"]) != PLATFORMS or not set(feature["validation"].values()) <= VALIDATION:
            raise ValueError(f"{name}: every feature needs three explicit validation states")
        if feature["complete"] and set(feature["validation"].values()) != {"native-tested"}:
            raise ValueError(f"{name}: source, research and native boundary checks cannot complete a three-client feature")
    application = json.loads((root / "apps/linux/application.json").read_text(encoding="utf-8"))
    components = json.loads((root / "tools/dependencies/components.json").read_text(encoding="utf-8"))["components"]
    for name in LINUX_COMPONENTS:
        if set(components.get(name, {}).get("targets", {})) != {"linux-x64"}:
            raise ValueError(f"{name}: Kotlin client dependencies must build and verify only on Linux")
    required = application.get("requiredSourceComponents", [])
    if not required or not set(required) <= set(components):
        raise ValueError("Linux application prerequisites must name registered source components")
    if application.get("applicationBuildReady") and any(components[name]["status"] != "ready" for name in required):
        raise ValueError("Unavailable source components cannot qualify a Linux application build")
    workflow = json.loads((root / ".github/workflows/repository.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    for platform in PLATFORMS:
        if platform not in jobs or platform not in jobs["required"]["needs"]:
            raise ValueError(f"{platform}: required client CI is missing")
    if (root / "apps/apple").exists() or any((root / "packages").glob("apple-*")):
        raise ValueError("Desktop implementation paths must use macos, windows and linux")


if __name__ == "__main__":
    check(Path(__file__).resolve().parents[2])
    print("Three-platform source structure and feature completion declarations are consistent")
