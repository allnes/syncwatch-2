"""Assemble an owned, relocatable native media SDK without copying build tools."""

from pathlib import Path
import re
import shutil
import subprocess
from source_profile import selected_plugins


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
    for name in selected_plugins(profile, context.target):
        matches = [p for p in (build / "modules/.libs").glob("lib" + name + "_plugin.*") if library(p)]
        if len(matches) != 1:
            raise ValueError("Missing or ambiguous selected VLC plugin: " + name)
        copy_library(matches[0], plugins)
    shutil.copytree(context.prefix / "include", destination / "include")
    include = destination / "include/vlc"
    include.mkdir(parents=True)
    for directory in [source / "include/vlc", build / "include/vlc"]:
        if directory.exists():
            for path in directory.glob("*.h"):
                shutil.copy2(path, include / path.name)
    if context.target == "windows-x64":
        imports = destination / "lib"
        imports.mkdir()
        for directory in [context.prefix / "lib", build / "lib/.libs"]:
            for path in directory.glob("*.dll.a"):
                shutil.copy2(path, imports / path.name)
    elif context.target == "linux-x64":
        fonts = destination / "share/fonts"
        fonts.mkdir(parents=True)
        # Font files are OS/user resources, never copied from the developer SDK.
        # This owned configuration keeps Fontconfig independent of its build prefix.
        (fonts / "fonts.conf").write_bytes(b'<?xml version="1.0"?>\n<fontconfig>\n'
            b'<dir>/usr/share/fonts</dir><dir>/usr/local/share/fonts</dir>\n'
            b'<dir prefix="xdg">fonts</dir><cachedir prefix="xdg">fontconfig</cachedir>\n'
            b'</fontconfig>\n')
    return libraries


def relocate(context, destination):
    binaries = sorted(p for p in destination.rglob("*") if p.is_file() and library(p))
    if context.target == "macos-arm64":
        owned = {p.name for p in binaries}
        for index, path in enumerate(binaries):
            output = subprocess.check_output(["otool", "-L", str(path)], text=True)
            commands = subprocess.check_output(["otool", "-l", str(path)], text=True)
            identities = re.findall(r"cmd LC_ID_DYLIB\s+cmdsize \d+\s+name (.*?) \(offset", commands)
            args = ["install_name_tool"]
            for identity in identities:
                # Linker aliases must retain the same upstream SONAME. Giving
                # each regular alias its own ID loads duplicate native images.
                if identity.startswith(str(context.prefix)):
                    identity = "@rpath/" + Path(identity).name
                if not identity.startswith("@rpath/") or "/" in identity.removeprefix("@rpath/"):
                    raise ValueError("Unexpected upstream native media identity")
                args.extend(["-id", identity])
            expected = "@loader_path/../../.." if "plugins" in path.parts else "@loader_path"
            rpaths = re.findall(r"cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset", commands)
            for rpath in rpaths:
                if rpath != expected:
                    args.extend(["-delete_rpath", rpath])
            if expected not in rpaths:
                args.extend(["-add_rpath", expected])
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
