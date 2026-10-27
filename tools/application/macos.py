"""Assemble the native Swift application with its default bundle runtime locations."""

import plistlib
import shutil
import subprocess

from candidate_tree import Component
from receipts import ROOT, require_host


def prepare(arguments, work):
    require_host("macos-arm64")
    binary = arguments.application.resolve(strict=True)
    architectures = subprocess.check_output(["lipo", "-archs", str(binary)], text=True).split()
    if "arm64" not in architectures:
        raise ValueError("Native macOS application must contain arm64 code")
    info = plistlib.loads((ROOT / "apps/macos/Resources/Info.plist").read_bytes())
    if info.get("CFBundleExecutable") != "SyncWatch" or info.get("CFBundleIdentifier") != "group.salo.syncwatch":
        raise ValueError("Application bundle identity differs from its native entry")
    bundle = work / "application"
    (bundle / "Contents/MacOS").mkdir(parents=True)
    shutil.copy2(binary, bundle / "Contents/MacOS/SyncWatch")
    (bundle / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
    shutil.copy2(ROOT / "LICENSE", bundle / "Contents/LICENSE")
    return [Component(bundle, "SyncWatch.app"),
            Component(arguments.media_package, "SyncWatch.app/Contents/Frameworks/Media"),
            Component(arguments.helper_package, "SyncWatch.app/Contents/Frameworks/Syncplay")]
