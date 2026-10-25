"""Build original Linux platform clients with no source patches or implicit downloads."""

from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/native"))
from native_context import BuildContext
from native_libraries import cmake, meson, zlib
from native_x11 import build as build_x11
import header_scope


def build(work, sources, epoch, offline):
    work.mkdir()
    context = BuildContext(work, epoch)
    for key in ("CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "LIBRARY_PATH"):
        context.env.pop(key, None)
    context.env.update(offline)
    context.env.update(PKG_CONFIG_LIBDIR=str(context.prefix / "lib/pkgconfig") + ":" + str(context.prefix / "share/pkgconfig"),
                       PKG_CONFIG_PATH="", PYTHON=sys.executable, PYTHONNOUSERSITE="1")
    context.env["CFLAGS"] += " -MD"
    context.env["CXXFLAGS"] += " -MD"
    context.env["LDFLAGS"] += " -Wl,-z,defs,-z,relro,-z,now"
    try:
        build_x11(context, sources)
        # The upstream include->src symlink is represented by an explicit original-header path.
        context.env["CFLAGS"] += " -I" + str(sources["desktop-libglvnd"] / "src/util/uthash/src")
        meson(context, sources, "desktop-libglvnd", ["-Dx11=enabled", "-Dglx=enabled", "-Degl=false",
                                                     "-Dhgl=false", "-Dgles1=false", "-Dgles2=false"])
        zlib(context, sources)
        cmake(context, "freetype", sources["freetype"], ["-DBUILD_SHARED_LIBS=ON", "-DFT_DISABLE_ZLIB=OFF",
            "-DZLIB_LIBRARY=" + str(context.prefix / "lib/libz.a"), "-DZLIB_INCLUDE_DIR=" + str(context.prefix / "include"),
            "-DFT_DISABLE_BZIP2=ON", "-DFT_DISABLE_PNG=ON", "-DFT_DISABLE_HARFBUZZ=ON", "-DFT_DISABLE_BROTLI=ON"])
        cmake(context, "expat", sources["expat"] / "expat", ["-DEXPAT_BUILD_TOOLS=OFF", "-DEXPAT_BUILD_EXAMPLES=OFF",
            "-DEXPAT_BUILD_TESTS=OFF", "-DEXPAT_BUILD_DOCS=OFF", "-DEXPAT_SHARED_LIBS=ON"])
        meson(context, sources, "fontconfig", ["-Dxml-backend=expat", "-Dtests=disabled", "-Dtests-external-fonts=disabled",
                                               "-Ddoc=disabled", "-Dtools=disabled", "-Dnls=disabled", "-Dcache-build=disabled"])
        meson(context, sources, "desktop-dbus", ["-Dmessage_bus=false", "-Dtools=false", "-Dmodular_tests=disabled",
            "-Dinstalled_tests=false", "-Dintrusive_tests=false", "-Dx11_autolaunch=disabled", "-Dsystemd=disabled",
            "-Dapparmor=disabled", "-Dselinux=disabled", "-Dlibaudit=disabled", "-Dxml_docs=disabled",
            "-Ddoxygen_docs=disabled", "-Dducktype_docs=disabled", "-Dqt_help=disabled"])
        context.header_count = header_scope.clients(context, sources)
        return context
    finally:
        retained = work.parent / "logs"
        for path in context.logs.iterdir():
            shutil.copy2(path, retained / ("platform-" + path.name))
        if (work / "commands.json").exists():
            shutil.copy2(work / "commands.json", retained / "platform-commands.json")


if __name__ == "__main__":
    import json
    import tempfile
    if sys.argv[1:] != ["sdk"]:
        raise SystemExit("Use platform_clients.py sdk to inspect developer build tools")
    with tempfile.TemporaryDirectory(prefix="desktop-native-sdk-") as temporary:
        context = BuildContext(Path(temporary), 0)
        print(json.dumps(context.sdk(), sort_keys=True))
