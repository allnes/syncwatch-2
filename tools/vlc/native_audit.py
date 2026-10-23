"""Reject native imports outside the owned package and declared OS/SDK boundary."""

from pathlib import Path
import re
import subprocess

from native_package import library

MAC_LIBRARIES = {"/usr/lib/libSystem.B.dylib", "/usr/lib/libiconv.2.dylib", "/usr/lib/libc++.1.dylib", "/usr/lib/libobjc.A.dylib"}
MAC_FRAMEWORKS = {"AppKit", "ApplicationServices", "Foundation", "CoreFoundation", "CoreServices", "CFNetwork", "Security",
                  "CoreMedia", "CoreVideo", "VideoToolbox", "CoreText", "CoreGraphics", "IOSurface", "Metal"}
LINUX_LIBRARIES = {"libc.so.6", "libm.so.6", "libpthread.so.0", "libdl.so.2", "librt.so.1",
                   "libgcc_s.so.1", "libstdc++.so.6", "ld-linux-x86-64.so.2"}
WINDOWS_LIBRARIES = {n.casefold() for n in ["advapi32.dll", "bcrypt.dll", "comctl32.dll", "crypt32.dll",
    "api-ms-win-core-synch-l1-2-0.dll",
    "d3d11.dll", "dwrite.dll", "dxgi.dll", "gdi32.dll", "imm32.dll", "iphlpapi.dll", "kernel32.dll",
    "msvcrt.dll", "ntdll.dll", "ole32.dll", "oleaut32.dll", "psapi.dll", "rpcrt4.dll", "secur32.dll",
    "setupapi.dll", "shell32.dll", "shlwapi.dll", "ucrtbase.dll", "user32.dll", "usp10.dll", "version.dll", "winmm.dll", "ws2_32.dll"]}


def imports(context, path):
    if context.target == "macos-arm64":
        text = subprocess.check_output(["otool", "-L", str(path)], text=True)
        dependencies = [line.strip().split(" (", 1)[0] for line in text.splitlines()[1:]]
        commands = subprocess.check_output(["otool", "-l", str(path)], text=True)
        identity = re.findall(r"cmd LC_ID_DYLIB\s+cmdsize \d+\s+name (.*?) \(offset", commands)
        dependencies = [name for name in dependencies if name not in identity]
        rpaths = re.findall(r"cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset", commands)
        expected = "@loader_path/../../.." if "plugins" in path.parts else "@loader_path"
        if rpaths != [expected]:
            raise ValueError("Native media has a foreign Mach-O runpath: " + path.name)
        return dependencies
    if context.target == "linux-x64":
        text = subprocess.check_output([context.tool("readelf"), "-d", str(path)], text=True)
        rpaths = re.findall(r"\((?:RPATH|RUNPATH)\).*?\[(.*?)\]", text)
        expected = "$ORIGIN/../../.." if "plugins" in path.parts else "$ORIGIN"
        if rpaths != [expected]:
            raise ValueError("Native media has a foreign ELF runpath: " + path.name)
        return re.findall(r"\(NEEDED\).*?\[(.*?)\]", text)
    text = subprocess.check_output([context.tool("objdump"), "-p", str(path)], text=True)
    return re.findall(r"DLL Name: (\S+)", text)


def system_import(target, name):
    if target == "macos-arm64":
        match = re.fullmatch(r"/System/Library/Frameworks/([A-Za-z0-9]+)\.framework/Versions/[A-Z]/\1", name)
        return name in MAC_LIBRARIES or bool(match and match[1] in MAC_FRAMEWORKS)
    if target == "linux-x64":
        return name in LINUX_LIBRARIES
    return name.casefold() in WINDOWS_LIBRARIES or bool(re.fullmatch(r"api-ms-win-crt-[a-z0-9-]+\.dll", name, re.I))


def audit(context, package):
    directory = package / ("bin" if context.target == "windows-x64" else "lib")
    owned = {p.name.casefold(): p for p in directory.iterdir() if p.is_file() and library(p)}
    result = {}
    for path in sorted(p for p in directory.rglob("*") if p.is_file() and library(p)):
        dependencies = imports(context, path)
        for name in dependencies:
            local = name.removeprefix("@rpath/")
            if local.casefold() in owned and "/" not in local and "\\" not in local:
                continue
            if not system_import(context.target, name):
                raise ValueError("Undeclared native media import " + path.name + " -> " + name)
        result[path.relative_to(package).as_posix()] = dependencies
    if not result:
        raise ValueError("Native media package contains no native libraries")
    return result
