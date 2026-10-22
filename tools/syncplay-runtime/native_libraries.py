"""Build selected upstream OpenSSL and libffi libraries with the identified SDK."""

from pathlib import Path
import shutil
import sys

from source_graph import ROOT

sys.path.insert(0, str(ROOT / "tools/python-build"))
from native_build import execute


def openssl(source, work, native, perl, environment):
    build, prefix, logs = (work / n for n in ["openssl-build", "openssl-sdk", "openssl-logs"])
    build.mkdir(); logs.mkdir()
    env = dict(environment, PERL5LIB=str(source / "external/perl/Text-Template-1.56/lib"))
    target = {"macos-arm64": "darwin64-arm64-cc", "linux-x64": "linux-x86_64", "windows-x64": "VC-WIN64A"}[native["target"]]
    flags = ["shared", "no-asm", "no-tests", "no-legacy", "no-comp", "no-engine", "no-module", "no-dso",
             "--prefix=" + prefix.as_posix(), "--libdir=lib"]
    if native["target"] == "windows-x64":
        env["CC"] = "cl"
    commands = {"configure": execute("configure", [str(perl), str(source / "Configure"), target, *flags], build, logs, env)}
    windows = native["target"] == "windows-x64"
    # CreateProcess searches the parent's PATH, not the supplied child PATH.
    # Resolve nmake from the identified MSVC SDK before spawning it.
    make = env["SYNCWATCH_NMAKE"] if windows else "make"
    commands["compile"] = execute("compile", [make, *([] if windows else ["-j4"]), "build_libs"], build, logs, env)
    commands["install"] = execute("install", [make, "install_dev"], build, logs, env)
    if native["target"] == "macos-arm64":
        for name in ["libcrypto.3.dylib", "libssl.3.dylib"]:
            commands["identity-" + name] = execute("identity-" + name,
                ["install_name_tool", "-id", "@rpath/" + name, str(prefix / "lib" / name)], build, logs, env)
        commands["crypto-reference"] = execute("crypto-reference", ["install_name_tool", "-change",
            str(prefix / "lib/libcrypto.3.dylib"), "@rpath/libcrypto.3.dylib", str(prefix / "lib/libssl.3.dylib")], build, logs, env)
    return prefix, commands


def libffi(source, work, native, environment):
    if native["target"] == "windows-x64":
        return None, {}  # CFFI's original MSVC port is compiled from its own sources.
    build, prefix, logs = (work / n for n in ["libffi-build", "libffi-sdk", "libffi-logs"])
    build.mkdir(); logs.mkdir()
    commands = {"autogen": execute("autogen", ["sh", "autogen.sh"], source, logs, environment)}
    commands["configure"] = execute("configure", ["sh", str(source / "configure"), "--prefix=" + str(prefix),
        "--disable-shared", "--enable-static", "--disable-docs", "--with-pic"], build, logs, environment)
    commands["compile"] = execute("compile", ["make", "-j4"], build, logs, environment)
    commands["install"] = execute("install", ["make", "install"], build, logs, environment)
    return prefix, commands
