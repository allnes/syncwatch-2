"""Keep complete notices for compiler support code used by the Windows SDK."""

import os
from pathlib import Path

from source_profile import ROOT
from source_files import encoded


def notices(context):
    if context.target != "windows-x64":
        return {}
    root = Path(os.environ.get("SYNCWATCH_VLC_MSYS_ROOT", ROOT / ".local/vlc-sdk/windows/msys64"))
    result = {}
    for name in ["gcc", "libgcc", "libstdc++", "crt", "headers", "libwinpthread", "winpthreads"]:
        directory = root / "ucrt64/share/licenses" / name
        paths = sorted(p for p in directory.rglob("*") if p.is_file())
        if not paths:
            raise ValueError("Compiler SDK runtime grants are missing: " + name)
        for path in paths:
            result["notices/compiler-sdk/" + name + "/" + path.relative_to(directory).as_posix()] = path.read_bytes()
    profile = (ROOT / "tools/vlc/windows-sdk.json").read_bytes()
    result["sources/compiler-sdk.json"] = profile
    result["sources/compiler-sdk-boundary.json"] = encoded({
        "compilerSdk": "MSYS2 UCRT GCC and MinGW-w64", "applicationLibrarySource": False,
        "runtimePolicy": "Static GCC/libstdc++ support; Windows APIs from the operating system",
        "unexpectedDllImportsRejected": True, "developerSdkPackaged": False})
    return result
