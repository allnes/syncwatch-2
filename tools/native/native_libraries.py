"""Shared offline recipes for original Meson, CMake and compression sources."""

from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def meson(context, sources, name, options):
    build = context.work / (name + "-build")
    command = [sys.executable, str(sources["meson"] / "meson.py")]
    binaries = context.meson_binaries()
    native = []
    if binaries:
        configuration = context.work / "meson-sdk-tools.ini"
        configuration.write_text("[binaries]\n" + "".join(key + " = " + repr(value) + "\n" for key, value in binaries.items()))
        native = ["--native-file=" + str(configuration)]
    context.run(name + "-configure", [*command, "setup", str(build), str(sources[name]),
        "--prefix=" + str(context.prefix), "--libdir=lib", "--buildtype=release",
        "--wrap-mode=nodownload", *native, "-Dauto_features=disabled", "-Ddefault_library=shared", *options])
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


