"""Assemble an owned, relocatable native media SDK without copying build tools."""

from pathlib import Path
import re
import shutil
import subprocess


def library(path):
    return path.suffix in {".dll", ".dylib"} or ".so" in path.name


def copy_library(source, directory):
    destination = directory / source.name
    if destination.exists() and destination.read_bytes() != source.read_bytes():
        raise ValueError("Native media library names collide: " + source.name)
    shutil.copy2(source, destination, follow_symlinks=True)


def assemble(context, build, source, profile, destination):
    destination.mkdir()
    libraries = destination / ("bin" if context.target == "windows-x64" else "lib")
    plugins = libraries / "vlc/plugins/selected"
    plugins.mkdir(parents=True)
    for directory in [context.prefix / "lib", context.prefix / "bin", build / "src/.libs", build / "lib/.libs"]:
        if directory.exists():
            for path in directory.iterdir():
                if path.is_file() and library(path):
                    copy_library(path, libraries)
    for name in profile["plugins"]:
        matches = [p for p in (build / "modules/.libs").glob("lib" + name + "_plugin.*") if library(p)]
        if len(matches) != 1:
            raise ValueError("Missing or ambiguous selected VLC plugin: " + name)
        copy_library(matches[0], plugins)
    include = destination / "include/vlc"
    include.mkdir(parents=True)
    for directory in [source / "include/vlc", build / "include/vlc"]:
        if directory.exists():
            for path in directory.glob("*.h"):
                shutil.copy2(path, include / path.name)
    if context.target == "windows-x64":
        imports = destination / "lib"
        imports.mkdir()
        for path in (build / "lib/.libs").glob("*.dll.a"):
            shutil.copy2(path, imports / path.name)
    return libraries


def relocate(context, destination):
    binaries = sorted(p for p in destination.rglob("*") if p.is_file() and library(p))
    if context.target == "macos-arm64":
        owned = {p.name for p in binaries}
        for index, path in enumerate(binaries):
            output = subprocess.check_output(["otool", "-L", str(path)], text=True)
            args = ["install_name_tool", "-id", "@rpath/" + path.name]
            for line in output.splitlines()[1:]:
                name = line.strip().split(" (", 1)[0]
                if name.startswith(str(context.prefix)):
                    if Path(name).name not in owned:
                        raise ValueError("Media dependency is absent from the owned package: " + name)
                    args.extend(["-change", name, "@rpath/" + Path(name).name])
            context.run("relocate-" + str(index), [*args, str(path)])
            context.run("sign-" + str(index), ["codesign", "--force", "--sign", "-", str(path)])
    elif context.target == "linux-x64":
        for index, path in enumerate(binaries):
            relative = "$ORIGIN/../../.." if "plugins" in path.parts else "$ORIGIN"
            context.run("relocate-" + str(index), [context.tool("patchelf"), "--set-rpath", relative, str(path)])
    return binaries
