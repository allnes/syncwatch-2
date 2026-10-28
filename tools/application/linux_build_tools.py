"""Build Xorg configure macros from the verified Media SDK's original source bytes."""

import hashlib
import json
from pathlib import Path
import sys

from receipts import ROOT, media, require_host

sys.path.insert(0, str(ROOT / "tools/native"))
sys.path.insert(0, str(ROOT / "tools/dependencies"))
from build import OFFLINE, checked_archive
from native_context import BuildContext
from native_x11 import autotools


def prepare(package, work):
    require_host("linux-x64")
    media(package, "linux-x64")
    profile = json.loads((ROOT / "tools/vlc/profile.json").read_text())
    specification = profile["sources"]["desktop-xorg-macros"]
    tree = work / "xorg-macros"
    tree.mkdir(parents=True)
    # Validate all original bytes before running their configure recipe. These
    # macros are build tools; they are never included in the application JVM.
    with checked_archive(package / "sources/desktop-xorg-macros.zip") as archive:
        if set(archive.namelist()) != set(specification["files"]):
            raise ValueError("Xorg macro source inventory differs")
        for name, expected in specification["files"].items():
            with archive.open(name) as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != expected:
                    raise ValueError("Xorg macro original source bytes differ")
        for name in specification["files"]:
            target = tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    context = BuildContext(work / "build", profile["sourceDateEpoch"])
    context.env.update(OFFLINE)
    autotools(context, {"desktop-xorg-macros": tree}, "desktop-xorg-macros")
    return context.prefix / "share/aclocal", Path(context.tool("autoreconf")).parent
