"""Bound native commands and keep developer SDKs outside the media payload."""

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys


def checksum(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def native_target():
    target = {("Darwin", "arm64"): "macos-arm64", ("Linux", "x86_64"): "linux-x64",
              ("Windows", "AMD64"): "windows-x64"}.get((platform.system(), platform.machine()))
    if not target:
        raise ValueError("A supported native media host is required")
    return target


def shell_path(path):
    text = Path(path).resolve().as_posix()
    if re.match(r"^[A-Za-z]:/", text):
        return "/" + text[0].lower() + text[2:]
    return text


class BuildContext:
    def __init__(self, work, epoch):
        self.work, self.target = work, native_target()
        self.logs = work / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.prefix = work / "prefix"
        self.prefix.mkdir(exist_ok=True)
        self.commands = {}
        self.env = dict(os.environ, SOURCE_DATE_EPOCH=str(epoch), PYTHONDONTWRITEBYTECODE="1",
                        CONFIG_SITE="/dev/null", GCRYPT_CONFIG="false")
        paths = []
        if self.target == "windows-x64":
            root = Path(os.environ["SYNCWATCH_VLC_MSYS_ROOT"]).resolve()
            paths.extend([root / "ucrt64/bin", root / "usr/bin"])
            self.shell = str(root / "usr/bin/bash.exe")
            self.env.update(MSYSTEM="UCRT64", MSYS2_PATH_TYPE="minimal", CHERE_INVOKING="1")
        else:
            for name in ["SYNCWATCH_VLC_EXTRA_TOOLS_ROOT", "SYNCWATCH_VLC_AUTOTOOLS_ROOT"]:
                if self.env.get(name):
                    root = Path(self.env[name]).resolve()
                    paths.append(root / "usr/bin")
            if self.target == "macos-arm64":
                paths.extend([Path("/opt/homebrew/opt/gettext/bin"), Path("/opt/homebrew/bin")])
            self.shell = "/bin/sh"
        self.env["PATH"] = os.pathsep.join(str(p) for p in paths) + os.pathsep + self.env["PATH"]
        for name, key in [("m4", "M4"), ("autoconf", "AUTOCONF"), ("automake", "AUTOMAKE"),
                          ("aclocal", "ACLOCAL"), ("autoreconf", "AUTORECONF"), ("autom4te", "AUTOM4TE"),
                          ("autoheader", "AUTOHEADER"),
                          ("glibtoolize" if self.target == "macos-arm64" else "libtoolize", "LIBTOOLIZE")]:
            path = self.tool(name)
            self.env[key] = shell_path(path) if self.target == "windows-x64" else path
        prefix = self.prefix.as_posix()
        self.env.update(PKG_CONFIG_PATH=prefix + "/lib/pkgconfig",
                        PKG_CONFIG_LIBDIR=prefix + "/lib/pkgconfig",
                        CFLAGS="-O2 -g0", CXXFLAGS="-O2 -g0", CPPFLAGS="-I" + prefix + "/include",
                        LDFLAGS="-L" + prefix + "/lib", CC="gcc", CXX="g++")
        if self.target == "macos-arm64":
            self.env.update(CC="clang", CXX="clang++", OBJC="clang", MACOSX_DEPLOYMENT_TARGET="13.0",
                            ac_cv_func_pipe2="no", ac_cv_func_dup3="no")
            for key in ["CFLAGS", "CXXFLAGS"]:
                self.env[key] += " -mmacosx-version-min=13.0"
            self.env["LDFLAGS"] += " -Wl,-rpath,@loader_path -Wl,-rpath,@loader_path/../../.."
        elif self.target == "windows-x64":
            self.env["LDFLAGS"] += " -static-libgcc -static-libstdc++"
        for name, relative in [("gettext_datadir", "usr/share/gettext"), ("BISON_PKGDATADIR", "usr/share/bison")]:
            root = self.env.get("SYNCWATCH_VLC_EXTRA_TOOLS_ROOT")
            if root:
                self.env[name] = str(Path(root) / relative)
        # Relocated Linux autotools retain their package-relative Perl/macro data.
        root = self.env.get("SYNCWATCH_VLC_AUTOTOOLS_ROOT")
        if root:
            root = Path(root)
            self.env["ACLOCAL_PATH"] = os.pathsep.join(str(p) for p in [root / "usr/share/aclocal", root / "usr/share/libtool/m4"])
            perl = [str(p) for p in (root / "usr/share").glob("automake-*")]
            if perl:
                self.env["PERL5LIB"] = os.pathsep.join(perl + [str(root / "usr/share/autoconf")])
                if len(perl) != 1:
                    raise ValueError("Select one relocated Automake data package")
                self.env["AUTOMAKE_LIBDIR"] = perl[0]
                self.env["ACLOCAL_AUTOMAKE_DIR"] = str(root / "usr/share" / Path(perl[0]).name.replace("automake-", "aclocal-"))
            self.env["AUTOM4TE_CFG"] = str(root / "usr/share/autoconf/autom4te.cfg")
            self.env["AC_MACRODIR"] = str(root / "usr/share/autoconf")

    def tool(self, name):
        path = shutil.which(name, path=self.env["PATH"])
        if not path:
            raise ValueError("Missing native media developer tool: " + name)
        return path

    def run(self, label, args, cwd=None, shell=False, env=None, timeout=3600):
        if label in self.commands:
            raise ValueError("Build command labels must be unique")
        directory = cwd or self.work
        if shell:
            args = [self.shell, "-c", "cd " + shlex.quote(shell_path(directory)) + " && " + shlex.join(args)]
        output = self.logs / (label + ".log")
        environment = dict(self.env, **(env or {}))
        print(label, flush=True)
        with output.open("wb") as log:
            process = subprocess.run(args, cwd=directory, env=environment, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        self.commands[label] = {"args": args, "logSha256": checksum(output), "exitCode": process.returncode}
        (self.work / "commands.json").write_text(json.dumps(self.commands, indent=2) + "\n")
        if process.returncode:
            raise ValueError(label + " failed:\n" + output.read_bytes()[-12000:].decode("utf-8", errors="replace"))

    def sdk(self):
        tools = {}
        for name in [self.env["CC"], self.env["CXX"], "make", "autoconf", "automake", "libtoolize" if self.target != "macos-arm64" else "glibtoolize", "pkg-config", "ninja", "cmake", "bison", "flex"]:
            path = self.tool(name)
            command = [path, "--version"]
            if self.target == "windows-x64":
                command = [self.shell, "-c", shlex.join([shell_path(path), "--version"])]
            result = subprocess.check_output(command, env=self.env, stderr=subprocess.STDOUT, timeout=30)
            tools[name] = {"sha256": checksum(path), "version": result.decode(errors="replace").splitlines()[0]}
        tools["buildPython"] = {"sha256": checksum(sys.executable), "version": sys.version.split()[0]}
        return {"target": self.target, "tools": tools, "sdkPackaged": False}
