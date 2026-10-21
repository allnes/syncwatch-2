"""Resolve and identify native build SDKs without downloading application code."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

from source_graph import ROOT
from toolchains import build_environment, resolve as rust_sdk

sys.path.insert(0, str(ROOT / "tools/python-build"))
from native_build import sdk_identity
from toolchain import checksum, output


def resolve():
    cmake, options, native = sdk_identity()
    rust, rust_identity = rust_sdk()
    environment = build_environment(rust)
    sdk_root = Path.home() / ".local/share/syncwatch/toolchains"
    candidates = [Path(shutil.which("perl") or "missing")]
    if native["target"] == "windows-x64":
        candidates += sorted(sdk_root.glob("strawberry-perl-*/original/perl/bin/perl.exe"), reverse=True)
    perl = next((p.resolve() for p in candidates if p.is_file() and (native["target"] != "windows-x64"
                 or output([str(p), "-e", 'print "$^V $^O"']).endswith("MSWin32"))), None)
    if perl is None:
        raise ValueError("Perl build SDK is required")
    perl_version = output([str(perl), "-e", 'print "$^V $^O"'])
    if native["target"] == "windows-x64" and not perl_version.endswith("MSWin32"):
        raise ValueError("MSVC OpenSSL requires native Windows Perl")
    identity = {"native": native, "rust": rust_identity,
                "perl": {"version": perl_version, "sha256": checksum(perl)}}
    environment["PATH"] = str(perl.parent) + os.pathsep + environment.get("PATH", "")
    if native["target"] == "windows-x64":
        instance = next(o.split("=", 1)[1] for o in options if o.startswith("-DCMAKE_GENERATOR_INSTANCE="))
        setup = Path(instance) / "VC/Auxiliary/Build/vcvarsall.bat"
        command = 'call "' + str(setup) + '" x64 >nul && set'
        result = subprocess.check_output(["cmd", "/d", "/s", "/c", command], text=True, timeout=60)
        environment.update((key.upper(), value) for key, value in (line.split("=", 1) for line in result.splitlines()
            if "=" in line and not line.startswith("=")))
        environment["PATH"] = str(rust / "bin") + os.pathsep + str(perl.parent) + os.pathsep + environment["PATH"]
        if checksum(shutil.which("cl", path=environment["PATH"])) != native["compilerSha256"]:
            raise ValueError("MSVC command environment differs from the selected C SDK")
    else:
        private = os.environ.get("SYNCWATCH_AUTOTOOLS_BIN")
        if private:
            environment["PATH"] = private + os.pathsep + environment["PATH"]
        identity["autotools"] = {}
        for name in ["m4", "autoconf", "automake", "aclocal", "autoreconf", "autom4te", "autoheader", "libtoolize"]:
            alternatives = [name, "glibtoolize"] if name == "libtoolize" else [name]
            path = next((shutil.which(n, path=environment["PATH"]) for n in alternatives
                         if shutil.which(n, path=environment["PATH"])), None)
            if path is None:
                raise ValueError("Required autotools SDK is missing: " + name)
            identity["autotools"][name] = {"version": output([path, "--version"]).splitlines()[0], "sha256": checksum(path)}
            environment[{"m4": "M4", "autoconf": "AUTOCONF", "automake": "AUTOMAKE", "aclocal": "ACLOCAL",
                         "autoreconf": "AUTORECONF", "autom4te": "AUTOM4TE", "autoheader": "AUTOHEADER",
                         "libtoolize": "LIBTOOLIZE"}[name]] = path
        environment["CC"] = next(o.split("=", 1)[1] for o in options if o.startswith("-DCMAKE_C_COMPILER="))
        if native["target"] == "macos-arm64":
            environment["MACOSX_DEPLOYMENT_TARGET"] = "13.0"
            environment["SDKROOT"] = next(o.split("=", 1)[1] for o in options if o.startswith("-DCMAKE_OSX_SYSROOT="))
    environment.update(SOURCE_DATE_EPOCH="1700000000", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
                       LC_ALL="C", CARGO_NET_OFFLINE="true")
    return cmake, options, native, rust, perl, environment, identity
