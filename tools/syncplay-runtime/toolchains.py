"""Explicitly provision the pinned Rust build SDK, never an application library."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def specification():
    data = json.loads(Path(__file__).with_name("toolchains.json").read_text(encoding="utf-8"))
    target = {("Darwin", "arm64"): "macos-arm64", ("Linux", "x86_64"): "linux-x64",
              ("Windows", "AMD64"): "windows-x64"}.get((platform.system(), platform.machine()))
    if data["schemaVersion"] != 1 or target not in data["targets"]:
        raise ValueError("Unsupported Rust build SDK target")
    return data, target


def verify(directory, spec, target):
    expected = {}
    for name, component in spec["targets"][target]["components"].items():
        archive = directory / "archives" / (name + ".tar.xz")
        if digest(archive) != component["sha256"]:
            raise ValueError("Rust SDK vendor archive differs")
        prefix = component["directory"] + "/" + component["component"] + "/"
        with tarfile.open(archive) as package:
            for entry in package:
                if not entry.name.startswith(prefix) or not entry.isfile():
                    continue
                relative = entry.name.removeprefix(prefix)
                if relative == "manifest.in":
                    continue
                data = package.extractfile(entry).read()
                value = hashlib.sha256(data).hexdigest()
                if relative in expected and expected[relative] != value:
                    raise ValueError("Rust SDK component collision")
                expected[relative] = value
    home = directory / "home"
    found = {}
    for path in home.rglob("*"):
        if path.is_symlink():
            raise ValueError("Unexpected alias in Rust build SDK")
        if path.is_file():
            found[path.relative_to(home).as_posix()] = digest(path)
    if expected != found or not expected:
        raise ValueError("Rust SDK installation differs from its pinned vendor components")
    suffix = ".exe" if target == "windows-x64" else ""
    version = subprocess.check_output([str(home / ("bin/rustc" + suffix)), "--version"], text=True, timeout=30).strip()
    if not version.startswith("rustc " + spec["rustVersion"] + " "):
        raise ValueError("Rust build SDK version differs")
    identity = {"target": target, "rustc": version,
                "rustcSha256": found["bin/rustc" + suffix], "cargoSha256": found["bin/cargo" + suffix],
                "installationSha256": hashlib.sha256(json.dumps(found, sort_keys=True).encode()).hexdigest()}
    return home, identity


def provision(directory, spec, target, archives=None):
    if directory.exists():
        return verify(directory, spec, target)
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rust-sdk-", dir=directory.parent) as temporary:
        work = Path(temporary)
        (work / "archives").mkdir()
        home = work / "home"
        home.mkdir()
        for name, component in spec["targets"][target]["components"].items():
            url = urllib.parse.urlsplit(component["url"])
            if (url.scheme != "https" or url.hostname != "static.rust-lang.org"
                    or url.username or url.password or url.query or url.fragment):
                raise ValueError("Rust SDK must use the pinned official vendor")
            archive = work / "archives" / (name + ".tar.xz")
            if archives:
                shutil.copyfile(archives / url.path.rsplit("/", 1)[-1], archive)
            else:
                urllib.request.urlretrieve(component["url"], archive)
            if digest(archive) != component["sha256"]:
                raise ValueError("Rust SDK download checksum mismatch")
            with tarfile.open(archive) as package:
                package.extractall(work / "originals", filter="data")
            original = work / "originals" / component["directory"] / component["component"]
            for path in original.rglob("*"):
                if path.name == "manifest.in":
                    continue
                if path.is_symlink():
                    raise ValueError("Unexpected SDK component alias")
                if path.is_file():
                    destination = home / path.relative_to(original)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if destination.exists() and digest(destination) != digest(path):
                        raise ValueError("SDK installation file collision")
                    shutil.copy2(path, destination)
        verify(work, spec, target)
        work.rename(directory)
    return verify(directory, spec, target)


def resolve():
    spec, target = specification()
    directory = Path.home() / ".local/share/syncwatch/toolchains" / ("rust-" + spec["rustVersion"] + "-" + target)
    return verify(directory, spec, target)


def build_environment(home, parent=None):
    environment = dict(os.environ if parent is None else parent)
    suffix = ".exe" if platform.system() == "Windows" else ""
    environment["PATH"] = str(home / "bin") + os.pathsep + environment.get("PATH", "")
    environment["RUSTC"] = str(home / ("bin/rustc" + suffix))
    environment["RUSTDOC"] = str(home / ("bin/rustdoc" + suffix))
    # The vendor's rust-objcopy is nested below rustlib and needs the SDK's
    # own LLVM library. This is a build-tool environment, not a runtime path.
    if platform.system() == "Darwin":
        environment["DYLD_FALLBACK_LIBRARY_PATH"] = str(home / "lib")
    return environment


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provision", action="store_true")
    parser.add_argument("--archives", type=Path)
    args = parser.parse_args()
    spec, target = specification()
    if args.archives and not args.provision:
        raise ValueError("SDK archives require explicit provisioning")
    directory = Path.home() / ".local/share/syncwatch/toolchains" / ("rust-" + spec["rustVersion"] + "-" + target)
    home, identity = provision(directory, spec, target, args.archives) if args.provision else verify(directory, spec, target)
    print(json.dumps(identity, sort_keys=True))
