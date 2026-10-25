"""Build original Linux platform clients with no source patches or implicit downloads."""

from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/native"))
from native_context import BuildContext
from native_libraries import cmake, meson, zlib
import header_scope


SHARED = ("--enable-shared", "--disable-static")
NO_SPECS = ("--disable-specs", "--without-xmlto", "--without-fop", "--without-xsltproc")


def autotools(context, sources, name, options=()):
    source = sources[name]
    match = re.search(r"AC_CONFIG_AUX_DIR\(\[?([^\]\)]+)", (source / "configure.ac").read_text())
    auxiliary = source / match.group(1) if match else source
    auxiliary.mkdir(exist_ok=True)
    for filename, path in context.auxiliary_files().items():
        shutil.copy2(path, auxiliary / filename)
    context.run(name + "-autoreconf", [context.env["AUTORECONF"], "-fiv"], cwd=source)
    build = context.work / (name + "-build")
    build.mkdir()
    context.run(name + "-configure", [str(source / "configure"), "--prefix=" + str(context.prefix),
                "--libdir=" + str(context.prefix / "lib"), *options], cwd=build)
    context.run(name + "-build", ["make", "-j4"], cwd=build)
    context.run(name + "-install", ["make", "install"], cwd=build)


def build(work, sources, epoch, offline):
    work.mkdir()
    context = BuildContext(work, epoch)
    for key in ("CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "LIBRARY_PATH"):
        context.env.pop(key, None)
    context.env.update(offline)
    context.env.update(PKG_CONFIG_LIBDIR=str(context.prefix / "lib/pkgconfig") + ":" + str(context.prefix / "share/pkgconfig"),
                       PKG_CONFIG_PATH="", PYTHON=sys.executable, PYTHONNOUSERSITE="1")
    context.env["ACLOCAL_PATH"] = str(context.prefix / "share/aclocal") + ":" + context.env.get("ACLOCAL_PATH", "")
    context.env["CFLAGS"] += " -MD"
    context.env["CXXFLAGS"] += " -MD"
    context.env["LDFLAGS"] += " -Wl,-z,defs,-z,relro,-z,now"
    try:
        autotools(context, sources, "desktop-xorg-macros")
        meson(context, sources, "desktop-xorgproto", [])
        autotools(context, sources, "desktop-xtrans", ["--disable-docs"])
        autotools(context, sources, "desktop-xcb-proto")
        meson(context, sources, "desktop-libxau", [])
        autotools(context, sources, "desktop-libxdmcp", [*SHARED, "--disable-docs", "--disable-unit-tests", *NO_SPECS[1:]])
        autotools(context, sources, "desktop-libxcb", [*SHARED, "--disable-devel-docs", "--without-doxygen"])
        for name in ("desktop-libx11", "desktop-libxext"):
            autotools(context, sources, name, [*SHARED, *NO_SPECS])
        for name in ("desktop-libxrender", "desktop-libxrandr"):
            autotools(context, sources, name, SHARED)
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
