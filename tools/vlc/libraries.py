"""Build the pinned codec, text and font libraries with implicit downloads disabled."""

from pathlib import Path
import shutil
import subprocess
import sys

from build_context import shell_path
from source_profile import ROOT, restore_iconv


def meson(context, sources, name, options):
    build = context.work / (name + "-build")
    command = [sys.executable, str(sources["meson"] / "meson.py")]
    context.run(name + "-configure", [*command, "setup", str(build), str(sources[name]),
        "--prefix=" + str(context.prefix), "--libdir=lib", "--buildtype=release",
        "--wrap-mode=nodownload", "-Dauto_features=disabled", "-Ddefault_library=shared", *options])
    context.run(name + "-build", [*command, "compile", "-C", str(build), "-j4"])
    context.run(name + "-install", [*command, "install", "-C", str(build), "--no-rebuild"])


def cmake(context, name, source, options):
    build = context.work / (name + "-build")
    command = context.tool("cmake")
    version = subprocess.check_output([command, "--version"], env=context.env, text=True).split()[2]
    policy = ["-DCMAKE_POLICY_VERSION_MINIMUM=3.5"] if int(version.split(".")[0]) >= 4 else []
    context.run(name + "-configure", [command, "-S", str(source), "-B", str(build), "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_C_COMPILER=" + context.tool(context.env["CC"]),
        "-DCMAKE_INSTALL_PREFIX=" + str(context.prefix), "-DCMAKE_INSTALL_LIBDIR=lib",
        "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF", "-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF",
        "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
        *(["-DCMAKE_INSTALL_NAME_DIR=@rpath"] if context.target == "macos-arm64" else []), *policy, *options])
    context.run(name + "-build", [command, "--build", str(build), "--parallel", "4"])
    context.run(name + "-install", [command, "--install", str(build)])


def zlib(context, sources):
    build = context.work / "zlib-build"
    command = context.tool("cmake")
    context.run("zlib-configure", [command, "-S", str(ROOT / "tools/compression"), "-B", str(build),
        "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_C_COMPILER=" + context.tool(context.env["CC"]),
        "-DSYNCWATCH_ZLIB_SOURCE=" + str(sources["zlib"])])
    context.run("zlib-build", [command, "--build", str(build), "--target", "zlibstatic", "--parallel", "4"])
    library = Path((build / "library-Release.txt").read_text())
    lib = context.prefix / "lib"
    (lib / "pkgconfig").mkdir(parents=True, exist_ok=True)
    (context.prefix / "include").mkdir(exist_ok=True)
    shutil.copy2(library, lib / "libz.a")
    for source in [sources["zlib"] / "zlib.h", build / "upstream/zconf.h"]:
        shutil.copy2(source, context.prefix / "include" / source.name)
    (lib / "pkgconfig/zlib.pc").write_text("prefix=" + context.prefix.as_posix() +
        "\nlibdir=${prefix}/lib\nincludedir=${prefix}/include\nName: zlib\nDescription: owned source-built zlib\n"
        "Version: 1.3.2\nLibs: -L${libdir} -lz\nCflags: -I${includedir}\n", encoding="utf-8", newline="\n")


def build(context, sources):
    zlib(context, sources)
    cmake(context, "libsamplerate", sources["libsamplerate"], ["-DBUILD_SHARED_LIBS=ON",
        "-DBUILD_TESTING=OFF", "-DLIBSAMPLERATE_EXAMPLES=OFF", "-DLIBSAMPLERATE_INSTALL=ON"])
    if context.target == "windows-x64":
        original = restore_iconv(sources["libiconv"])
        build = context.work / "iconv-build"
        build.mkdir()
        context.run("iconv-configure", [shell_path(original / "configure"),
            "--prefix=" + shell_path(context.prefix), "--enable-shared", "--disable-static",
            "--disable-nls", "--disable-rpath", "--host=x86_64-w64-mingw32",
            "--build=x86_64-pc-msys"], cwd=build, shell=True)
        # Only the LGPL libraries and headers are built/installed, not the CLI.
        for part in ["libcharset", "lib"]:
            context.run("iconv-" + part, ["make", "-C", part, "-j4", "all", "install"], cwd=build, shell=True)
        # The top-level install recipe copies this configured public header.
        # include/ has no Makefile; top-level all also builds the GPL CLI.
        shutil.copy2(build / "include/iconv.h.inst", context.prefix / "include/iconv.h")
    cmake(context, "freetype", sources["freetype"], ["-DBUILD_SHARED_LIBS=ON", "-DFT_DISABLE_ZLIB=OFF",
        "-DZLIB_LIBRARY=" + str(context.prefix / "lib/libz.a"), "-DZLIB_INCLUDE_DIR=" + str(context.prefix / "include"),
        "-DFT_DISABLE_BZIP2=ON", "-DFT_DISABLE_PNG=ON", "-DFT_DISABLE_HARFBUZZ=ON", "-DFT_DISABLE_BROTLI=ON"])
    meson(context, sources, "harfbuzz", ["-Dfreetype=enabled", "-Dtests=disabled", "-Dutilities=disabled",
        "-Ddocs=disabled", "-Dsubset=disabled", "-Draster=disabled", "-Dvector=disabled", "-Dgpu=disabled"])
    meson(context, sources, "fribidi", ["-Ddocs=false", "-Dbin=false", "-Dtests=false"])
    if context.target == "linux-x64":
        cmake(context, "expat", sources["expat"] / "expat", ["-DEXPAT_BUILD_TOOLS=OFF", "-DEXPAT_BUILD_EXAMPLES=OFF",
            "-DEXPAT_BUILD_TESTS=OFF", "-DEXPAT_BUILD_DOCS=OFF", "-DEXPAT_SHARED_LIBS=ON"])
        meson(context, sources, "fontconfig", ["-Dxml-backend=expat", "-Dtests=disabled",
            "-Dtests-external-fonts=disabled", "-Ddoc=disabled", "-Dtools=disabled", "-Dnls=disabled", "-Dcache-build=disabled"])
    provider = {"macos-arm64": "coretext", "windows-x64": "directwrite", "linux-x64": "fontconfig"}[context.target]
    meson(context, sources, "libass", ["-D" + provider + "=enabled", "-Dlibunibreak=disabled", "-Dasm=enabled"])
    meson(context, sources, "dav1d", ["-Denable_tools=false", "-Denable_tests=false",
        "-Denable_examples=false", "-Denable_docs=false"])
    build = context.work / "ffmpeg-build"
    build.mkdir()
    flags = ["--prefix=" + shell_path(context.prefix), "--disable-autodetect", "--disable-programs", "--disable-doc",
        "--disable-network", "--disable-avdevice", "--disable-avfilter", "--disable-encoders", "--disable-muxers",
        "--disable-gpl", "--disable-nonfree", "--disable-version3", "--disable-debug", "--disable-static", "--enable-shared",
        "--cc=" + context.env["CC"], "--cxx=" + context.env["CXX"],
        "--enable-zlib", "--enable-libdav1d", "--extra-cflags=" + context.env["CPPFLAGS"] + " " + context.env["CFLAGS"],
        "--extra-ldflags=" + context.env["LDFLAGS"]]
    if context.target == "macos-arm64":
        flags.extend(["--enable-videotoolbox", "--install-name-dir=@rpath"])
    elif context.target == "windows-x64":
        flags.extend(["--target-os=mingw32", "--arch=x86_64", "--enable-d3d11va", "--pkg-config=pkg-config"])
    context.run("ffmpeg-configure", [shell_path(sources["ffmpeg"] / "configure"), *flags], cwd=build, shell=True)
    context.run("ffmpeg-build", ["make", "-j4"], cwd=build, shell=True)
    context.run("ffmpeg-install", ["make", "install"], cwd=build, shell=True)
