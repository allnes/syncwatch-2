"""Verified Kotlin developer compiler SDK; never an application classpath."""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import urllib.request
import zipfile

import jdk
from build_support import digest, java_environment, tools


ROOT = Path(__file__).resolve().parents[2]
SBOM = "vendor.spdx.json"


def specification():
    spec = json.loads((ROOT / "tools/jvm/kotlin_toolchain.json").read_text())
    validate_spec(spec)
    return spec


def validate_spec(spec):
    if spec["schemaVersion"] != 1 or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", spec["version"]):
        raise ValueError("Unsupported Kotlin compiler SDK specification")
    base = "https://github.com/JetBrains/kotlin/releases/download/v" + spec["version"] + "/kotlin-compiler-" + spec["version"]
    for key, suffix in (("archive", ".zip"), ("sbom", ".spdx.json")):
        item = spec[key]
        if item["url"] != base + suffix or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) or not 0 < item["bytes"] < 200_000_000:
            raise ValueError("Kotlin SDK requires an exact official release and checksum")
    if not set(spec["compilerFiles"]) <= spec["files"].keys() or not any(n.startswith("kotlinc/license/") for n in spec["files"]):
        raise ValueError("Compiler SDK inventory must include its complete vendor notices")


def checked_file(path, expected):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != expected["bytes"] or jdk.sha(path) != expected["sha256"]:
        raise ValueError("Kotlin developer SDK download differs from its pin")


def extract(archive, destination, spec):
    with zipfile.ZipFile(archive) as source:
        names, found, size = set(), set(), 0
        for item in source.infolist():
            name = item.orig_filename
            parts = PurePosixPath(name).parts
            if (not parts or any(p in {".", ".."} for p in parts) or name.startswith("/")
                    or "\\" in name or ":" in name or "\x00" in name or name.casefold() in names
                    or item.external_attr >> 16 & 0o170000 not in {0, 0o100000, 0o040000}):
                raise ValueError("Kotlin SDK archive contains an unsafe or duplicate path")
            names.add(name.casefold())
            if item.is_dir():
                continue
            size += item.file_size
            if name not in spec["files"] or item.file_size > 100_000_000 or size > 400_000_000:
                raise ValueError("Kotlin SDK archive differs from its complete file inventory")
            data = source.read(item)
            if digest(data) != spec["files"][name]:
                raise ValueError("Kotlin SDK vendor file checksum mismatch: " + name)
            found.add(name)
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        if found != set(spec["files"]):
            raise ValueError("Kotlin SDK archive is missing vendor files or notices")


def verify(directory, spec):
    if directory.is_symlink():
        raise ValueError("Kotlin SDK installation must not be a symbolic link")
    expected = spec["files"] | {SBOM: spec["sbom"]["sha256"]}
    actual = {}
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError("Kotlin SDK installation contains a symbolic link")
        if path.is_file():
            actual[path.relative_to(directory).as_posix()] = jdk.sha(path)
    if actual != expected:
        raise ValueError("Kotlin SDK installation differs from the complete vendor files and notices")
    checked_file(directory / SBOM, spec["sbom"])
    return directory


def home(root=ROOT):
    spec = specification()
    return verify(root / ".local/toolchains" / ("kotlin-" + spec["version"]), spec)


def provision(spec, directory, archive=None, sbom=None):
    validate_spec(spec)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / ("kotlin-" + spec["version"])
    if destination.exists():
        return verify(destination, spec)
    with tempfile.TemporaryDirectory(prefix="kotlin-provision-", dir=directory) as temporary:
        work = Path(temporary)
        inputs = {}
        for name, local in (("archive", archive), ("sbom", sbom)):
            path = Path(local) if local is not None else work / name
            if local is None:
                urllib.request.urlretrieve(spec[name]["url"], path)
            checked_file(path, spec[name])
            inputs[name] = path
        unpacked = work / "sdk"
        unpacked.mkdir()
        extract(inputs["archive"], unpacked, spec)
        (unpacked / SBOM).write_bytes(inputs["sbom"].read_bytes())
        verify(unpacked, spec)
        unpacked.rename(destination)
    return destination


def argument_file(arguments, path):
    """UTF-8 Kotlin/javac tool argfiles avoid command limits and shell parsing."""
    def quote(value):
        value = str(value)
        if any(c in value for c in "\x00\r\n"):
            raise ValueError("Java arguments must not contain NUL or newlines")
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    path.write_text("\n".join(quote(v) for v in arguments) + "\n", encoding="utf-8")


def java(arguments, directory, jdk_home):
    # The Windows native launcher decodes @files using the host ANSI code page.
    # Keep the short VM command on the Unicode process API; tools read long UTF-8
    # argument lists themselves. Do not change a workstation's locale or code page.
    return subprocess.check_output([tools(jdk_home)["java"], "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8",
                                    "-Dstderr.encoding=UTF-8", *map(str, arguments)], cwd=directory,
                                   env=java_environment(), stderr=subprocess.STDOUT, text=True, encoding="utf-8")


def compile(arguments, directory, jdk_home, compiler_home=None):
    compiler_home = compiler_home or home()
    spec = specification()
    for index, argument in enumerate(arguments):
        flag, separator, value = str(argument).partition("=")
        if flag in {"-include-runtime", "-kotlin-home", "-Xplugin", "-Xcompiler-plugin"}:
            raise ValueError("Compiler SDK runtimes and optional plugins are not application build inputs")
        if flag in {"-classpath", "-cp"}:
            value = value if separator else arguments[index + 1]
            for name in value.split(os.pathsep):
                if Path(name).resolve().is_relative_to(compiler_home.resolve()):
                    raise ValueError("Compiler SDK JARs must not enter the application classpath")
    explicit = [a for a in arguments if a not in {"-no-stdlib", "-no-reflect"}]
    with tempfile.TemporaryDirectory(prefix="kotlin-args-") as temporary:
        path = Path(temporary) / "arguments.txt"
        argument_file(["-no-stdlib", "-no-reflect", *explicit], path)
        command = ["-Xmx3g", "-Djava.awt.headless=true", "-cp",
                   str(compiler_home / spec["compilerFiles"][0]), spec["compilerEntry"], "@" + str(path)]
        try:
            return java(command, directory, jdk_home)
        except subprocess.CalledProcessError as error:
            print(error.output)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provision", action="store_true")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--sbom", type=Path)
    args = parser.parse_args()
    spec = specification()
    if (args.archive or args.sbom) and not args.provision:
        raise ValueError("Local SDK inputs require explicit provisioning")
    directory = provision(spec, ROOT / ".local/toolchains", args.archive, args.sbom) if args.provision else home()
    version = compile(["-version", "-no-stdlib", "-no-reflect"], ROOT, jdk.home(), directory).splitlines()[0]
    if not version.startswith("info: " + spec["compilerVersion"] + " "):
        raise ValueError("Kotlin compiler version differs from its exact pin")
    print("Kotlin compiler SDK " + spec["version"])


if __name__ == "__main__":
    main()
