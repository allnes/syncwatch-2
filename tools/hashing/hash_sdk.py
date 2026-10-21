"""Reuse installed C SDK discovery and identify its native symbol inspector."""

from pathlib import Path
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "compression"))
from toolchain import checksum, executable, output, resolve as c_sdk


def resolve():
    cmake, arguments, identity = c_sdk()
    if platform.system() == "Windows":
        location = next(a.split("=", 1)[1] for a in arguments if a.startswith("-DCMAKE_GENERATOR_INSTANCE="))
        home = Path(location)
        version = (home / "VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt").read_text(encoding="utf-8").strip()
        symbols = home / "VC/Tools/MSVC" / version / "bin/Hostx64/x64/dumpbin.exe"
    else:
        symbols = Path(output(["xcrun", "--find", "nm"]) if platform.system() == "Darwin" else executable("nm"))
    identity = identity | {"symbolToolSha256": checksum(symbols)}
    return cmake, arguments, identity, str(symbols)
