"""Build original Linux Skia/JNI objects; a linked desktop runtime is a separate gate."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

from native_sources import ROOT, digest, encoded, jni_units, legal_files, materialize, profile_data, snapshots, source_archive
from generators import headers
from build import OFFLINE
import header_scope

sys.path.insert(0, str(ROOT / "tools/jvm"))
import jdk


COMPONENT = "skiko-native-objects"


class Context:
    def __init__(self, work, profile):
        self.work = work
        self.logs = work / "logs"
        self.logs.mkdir(parents=True)
        self.env = dict(os.environ, SOURCE_DATE_EPOCH=str(profile["sourceDateEpoch"]), GIT_CEILING_DIRECTORIES=str(work),
                        CC="gcc", CXX="g++", **OFFLINE)
        # Developer SDK inputs cannot inject an undeclared application header/library.
        for name in ("CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "LIBRARY_PATH", "LD_LIBRARY_PATH"):
            self.env.pop(name, None)

    def run(self, name, command, *, cwd=None, output=False, timeout=600):
        (self.logs / (name + ".command.json")).write_bytes(encoded({"arguments": list(map(str, command)), "cwd": str(cwd) if cwd else None}))
        result = subprocess.run(list(map(str, command)), cwd=cwd, env=self.env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        (self.logs / (name + ".log")).write_bytes(result.stdout)
        if result.returncode:
            raise ValueError(name + " failed; inspect the retained original command log")
        return result.stdout if output else None


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def png_fixture():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\0" + b"".join(b"\x00\x00\xff\xff" if (x+y) % 2 else b"\xff\x00\x00\xff"
                                    for x in range(8)) for y in range(8))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def probe(context, payload, trees):
    fixture, binary = context.work / "checker.png", context.work / "native-consumer"
    fixture.write_bytes(png_fixture())
    archives = sorted((payload / "lib").glob("*.a"))
    context.run("consumer-link", ["g++", "-std=c++20", "-D_GLIBCXX_USE_CXX11_ABI=0", "-I" + str(trees["skia"]),
        ROOT / "tools/desktop/probe.cc", "-o", binary, "-Wl,-z,defs,-z,relro,-z,now", "-Wl,--start-group", *archives,
        "-Wl,--end-group", "-ldl", "-pthread"])
    if context.run("consumer-run", [binary, fixture], output=True).strip() != b"SYNCWATCH_NATIVE_PNG_OK":
        raise ValueError("Native Skia decoder did not reproduce the independent PNG fixture")


def build(context, payload, originals, profile, trees, generated):
    gn_work = context.work / "gn-build"
    gn_work.mkdir()
    write(gn_work / "last_commit_position.h", generated["gn/last_commit_position.h"])
    context.run("gn-configure", [sys.executable, trees["gn"] / "build/gen.py", "--no-last-commit-position",
                                 "--out-path", gn_work])
    context.run("gn-build", ["ninja", "-C", gn_work, "-j4", "gn"])
    gn = gn_work / "gn"
    version = profile["gnVersion"]
    expected = str(version["commitPosition"]) + " (" + version["commitAbbreviation"] + ")"
    if context.run("gn-version", [gn, "--version"], output=True).decode().strip() != expected:
        raise ValueError("Source-built GN does not describe the pinned original source")
    header_root = context.work / "scoped-headers"
    for name, data in generated.items():
        if not name.startswith("gn/"):
            write(header_root / name, data)
    abi = context.work / "header-abi.c"
    abi.write_text('#include <dbus/dbus.h>\n#include <fontconfig/fontconfig.h>\n'
                   '_Static_assert(sizeof(dbus_int64_t)==8 && sizeof(dbus_uint64_t)==8, "int64 ABI");\n'
                   '_Static_assert(sizeof(dbus_int32_t)==4 && sizeof(dbus_int16_t)==2, "integer ABI");\n'
                   '_Static_assert(sizeof(void*)==DBUS_SIZEOF_VOID_P, "pointer ABI");\n')
    context.run("header-abi", ["gcc", "-std=c11", "-Werror", "-I" + str(header_root),
                                "-I" + str(trees["desktop-dbus"]), "-fsyntax-only", abi])
    includes = [header_root, *[trees[name] / "include" for name in
                ("desktop-libglvnd", "desktop-libx11", "desktop-xorgproto", "desktop-libxrandr", "desktop-libxrender")]]
    arguments = profile["gnArguments"] + ["extra_cflags=" + json.dumps(["-MD", *["-I" + str(p) for p in includes]])]
    output = context.work / "skia-build"
    context.run("skia-configure", [gn, "gen", output, "--fail-on-unused-args", "--args=" + " ".join(arguments)], cwd=trees["skia"])
    context.run("skia-build", ["ninja", "-C", output, "-j4", *profile["skiaTargets"]], timeout=3600)
    dependencies = context.run("skia-header-dependencies", ["ninja", "-C", output, "-t", "deps"], output=True).decode()
    archives = sorted(output.glob("*.a"))
    if [p.name for p in archives] != profile["nativeArchives"]:
        raise ValueError("Native archive graph differs from the selected movie/UI profile")
    for path in archives:
        write(payload / "lib" / path.name, path.read_bytes())
    cpp = trees["skiko"] / "skiko"
    home = jdk.home()
    jni_headers = [home / "include", home / "include/linux", *[trees["skia"] / name for name in profile["jni"]["skiaIncludes"]],
                   cpp / "src/awtMain/cpp/include", cpp / "src/jvmMain/cpp/common", cpp / "src/jvmMain/cpp/include",
                   cpp / "src/commonMain/cpp/common/include", *includes, trees["desktop-dbus"]]
    sources = jni_units(profile)
    flags = ["-std=c++20", "-O3", *profile["jni"]["defines"], "-DGL_GLEXT_PROTOTYPES", "-fPIC",
             "-fno-rtti", "-fno-exceptions", "-fvisibility=hidden", "-fvisibility-inlines-hidden",
             "-ffile-prefix-map=" + str(context.work) + "=/syncwatch-native", *["-I" + str(p) for p in jni_headers]]
    commands = []
    depfiles = []
    for name in sources:
        object_ = payload / "objects" / (name + ".o")
        object_.parent.mkdir(parents=True, exist_ok=True)
        depfile = context.logs / ("jni-" + name.replace("/", "-") + ".d")
        depfiles.append(depfile)
        commands.append((name, ["g++", *flags, "-MD", "-MF", depfile, "-c", trees["skiko"] / name, "-o", object_]))
    def compile_(item):
        name, command = item
        context.run("jni-" + name.replace("/", "-"), command, timeout=180)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(compile_, commands))
    paths = header_scope.ninja_paths(dependencies, output)
    for depfile in depfiles:
        paths.extend(header_scope.make_paths(depfile.read_text()))
    compiler_include = Path(context.run("compiler-header-root", ["gcc", "-print-file-name=include"], output=True).decode().strip()).resolve()
    original_paths = {(trees[name] / path).resolve() for name, files in originals.items() for path in files}
    header_scope.verify(paths, original_paths, [header_root.resolve(), output.resolve() / "gen"], compiler_include, home.resolve() / "include")
    write(payload / "tools/gn", gn.read_bytes())
    (payload / "tools/gn").chmod(0o755)
    write(payload / "sources.zip", source_archive(originals, profile, generated))
    for name, data in legal_files(originals, profile).items():
        write(payload / name, data)
    probe(context, payload, trees)
    files = {p.relative_to(payload).as_posix(): digest(p.read_bytes()) for p in payload.rglob("*") if p.is_file()}
    report = {"profile": profile["profile"], "sources": len(originals), "archives": len(archives), "jniObjects": len(sources),
              "nativeRendererLinked": False, "nativeRuntimeQualified": False, "physicalOutputAccepted": False, "files": files}
    write(payload / "native-objects.json", encoded(report))


def verify(payload, originals, profile, generated):
    report = json.loads((payload / "native-objects.json").read_text())
    files = {p.relative_to(payload).as_posix(): digest(p.read_bytes()) for p in payload.rglob("*")
             if p.is_file() and p != payload / "native-objects.json"}
    if (any(p.is_symlink() for p in payload.rglob("*")) or report["files"] != files
            or report["profile"] != profile["profile"] or report["sources"] != len(originals)
            or report["archives"] != len(profile["nativeArchives"]) or report["jniObjects"] != len(jni_units(profile))
            or any(report[key] is not False for key in ("nativeRendererLinked", "nativeRuntimeQualified", "physicalOutputAccepted"))):
        raise ValueError("Native object payload or acceptance scope changed")
    if (payload / "sources.zip").read_bytes() != source_archive(originals, profile, generated):
        raise ValueError("Original native source, grant, generator or profile changed")
    if any((payload / path).read_bytes() != data for path, data in legal_files(originals, profile).items()):
        raise ValueError("Native original grant or scope notice changed")
    expected = ({"lib/" + name for name in profile["nativeArchives"]}
                | {"objects/" + name + ".o" for name in jni_units(profile)}
                | set(legal_files(originals, profile)) | {"tools/gn", "sources.zip"})
    if set(files) != expected:
        raise ValueError("Native payload has missing or unexpected objects/archives/files")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "verify"))
    parser.add_argument("--platform", choices=("linux-x64",))
    args = parser.parse_args()
    if (platform.system(), platform.machine()) != ("Linux", "x86_64"):
        raise ValueError("Native Linux renderer objects require their actual target host")
    profile = profile_data()
    archive = args.operation == "verify"
    directory = ROOT / "artifacts/dependencies" / COMPONENT / "linux-x64"
    originals = snapshots(directory if archive else Path(os.environ["SYNCWATCH_DEPENDENCY_SOURCES"]), profile, archive=archive)
    generated = headers(originals, profile)
    payload = directory / "payload" if archive else Path(os.environ["SYNCWATCH_DEPENDENCY_OUTPUT"])
    if not archive and json.loads(os.environ["SYNCWATCH_DEPENDENCY_FLAGS"]) != {"profile": profile["profile"]}:
        raise ValueError("Unknown native renderer object profile")
    with tempfile.TemporaryDirectory(prefix="native-objects-") as temporary:
        context = Context(Path(temporary), profile)
        trees = materialize(context.work / "sources", originals, profile)
        try:
            if archive:
                verify(payload, originals, profile, generated)
                probe(context, payload, trees)
            else:
                build(context, payload, originals, profile, trees, generated)
                verify(payload, originals, profile, generated)
        finally:
            retained = directory / ("verify-logs" if archive else "build-logs")
            retained.mkdir(parents=True, exist_ok=True)
            for path in context.logs.iterdir():
                shutil.copy2(path, retained / path.name)
    print("Original source-built GN, 26 Skia archives and 105 JNI objects verified; native runtime and desktop acceptance remain open")


if __name__ == "__main__":
    main()
