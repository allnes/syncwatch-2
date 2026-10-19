"""Resolve installed native build SDKs without downloading or packaging them."""

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess


def output(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=30).strip()


def executable(name, alternatives=()):
    found = shutil.which(name)
    if not found:
        found = next((str(p) for p in alternatives if p.is_file()), None)
    if not found:
        raise ValueError("Required developer SDK tool is unavailable: " + name)
    return str(Path(found).resolve())


def checksum(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def visual_studio_generator(installation_version, cmake_version):
    major = int(installation_version.split(".")[0])
    if major == 17:
        return "Visual Studio 17 2022", "v143"
    if major == 18:
        if cmake_version < (4, 2):
            raise ValueError("Visual Studio 2026 requires CMake 4.2 or newer")
        return "Visual Studio 18 2026", "v145"
    raise ValueError("Visual Studio 2022 or 2026 x64 C SDK is required")


def resolve():
    system, machine = platform.system(), platform.machine()
    target = {("Darwin", "arm64"): "macos-arm64", ("Linux", "x86_64"): "linux-x64",
              ("Windows", "AMD64"): "windows-x64", ("Windows", "x86_64"): "windows-x64"}.get((system, machine))
    if not target:
        raise ValueError("Native compression SDK requires a supported host architecture")
    isolated = Path.home() / ".local/share/syncwatch/toolchains"
    candidates = [Path("/opt/homebrew/bin/cmake"), Path("/Applications/CMake.app/Contents/bin/cmake")]
    candidates += sorted(isolated.glob("cmake-*/cmake-*/CMake.app/Contents/bin/cmake"))
    cmake = executable("cmake", candidates)
    version = output([cmake, "--version"]).splitlines()[0]
    match = re.fullmatch(r"cmake version (\d+)\.(\d+)\.\d+", version)
    if not match or not ((3, 30) <= tuple(map(int, match.groups())) < (5, 0)):
        raise ValueError("CMake 3.30 through 4.x is required")
    identity = {"target": target, "cmake": version, "cmakeSha256": checksum(cmake)}
    configure = []
    if system == "Windows":
        installer = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
        installations = json.loads(output([str(installer), "-latest", "-products", "*", "-version", "[17.0,19.0)",
                                          "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-format", "json", "-utf8"]))
        if not installations:
            raise ValueError("Visual Studio 2022 or 2026 x64 C SDK is required")
        selected = installations[0]
        generator, platform_toolset = visual_studio_generator(selected["installationVersion"], tuple(map(int, match.groups())))
        location = selected["installationPath"]
        home = Path(location)
        toolset = (home / "VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt").read_text().strip()
        compiler = home / "VC/Tools/MSVC" / toolset / "bin/Hostx64/x64/cl.exe"
        kits = Path(os.environ["ProgramFiles(x86)"]) / "Windows Kits/10/Include"
        versions = [p.name for p in kits.iterdir() if re.fullmatch(r"10\.0\.\d+\.0", p.name) and (p / "um/Windows.h").is_file()]
        if not versions:
            raise ValueError("Windows 10/11 platform SDK is required")
        sdk = max(versions, key=lambda v: tuple(map(int, v.split("."))))
        identity.update(compiler="MSVC " + toolset, compilerSha256=checksum(compiler), sdk=sdk, generator=generator,
                        archiverSha256=checksum(compiler.with_name("lib.exe")), linkerSha256=checksum(compiler.with_name("link.exe")))
        configure = ["-G", generator, "-A", "x64", "-T", platform_toolset + ",version=" + toolset + ",host=x64",
                     "-DCMAKE_GENERATOR_INSTANCE=" + location, "-DCMAKE_SYSTEM_VERSION=" + sdk]
    else:
        compiler = output(["xcrun", "--find", "clang"]) if system == "Darwin" else executable("cc")
        archiver = output(["xcrun", "--find", "ar"]) if system == "Darwin" else executable("ar")
        make = executable("make")
        identity.update(compiler=output([compiler, "--version"]).splitlines()[0], compilerSha256=checksum(compiler),
                        archiverSha256=checksum(archiver), make=output([make, "--version"]).splitlines()[0], makeSha256=checksum(make))
        configure = ["-G", "Unix Makefiles", "-DCMAKE_C_COMPILER=" + compiler, "-DCMAKE_AR=" + archiver,
                     "-DCMAKE_MAKE_PROGRAM=" + make]
        if system == "Darwin":
            sdk = output(["xcrun", "--sdk", "macosx", "--show-sdk-path"])
            identity["sdk"] = output(["xcrun", "--sdk", "macosx", "--show-sdk-version"])
            configure += ["-DCMAKE_OSX_SYSROOT=" + sdk, "-DCMAKE_OSX_ARCHITECTURES=arm64", "-DCMAKE_OSX_DEPLOYMENT_TARGET=13.0"]
    return cmake, configure, identity


if __name__ == "__main__":
    print(json.dumps(resolve()[2], sort_keys=True))
