"""Provision the exact developer JDK; this SDK is not an application runtime."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile

from build_support import java_environment


ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(root):
    records = {}
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("SDK symlink leaves its installation")
            records[name] = {"link": os.readlink(path)}
        elif path.is_file():
            records[name] = {"sha256": sha(path)}
    return records


def inventory_digest(records):
    return hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def current_target():
    targets = {("Darwin", "arm64"): "macos-arm64", ("Linux", "x86_64"): "linux-x64", ("Windows", "AMD64"): "windows-x64"}
    target = targets.get((platform.system(), platform.machine()))
    if target is None:
        raise ValueError("Unsupported developer JDK platform")
    return target


def extract(archive, destination):
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            names = [item.filename for item in source.infolist()]
            if len(names) != len({n.casefold() for n in names}):
                raise ValueError("SDK archive has duplicate/case-colliding paths")
            for item in source.infolist():
                if ("\\" in item.filename or not (destination / item.filename).resolve().is_relative_to(destination.resolve())
                        or item.external_attr >> 16 & 0o170000 not in {0, 0o100000, 0o040000}):
                    raise ValueError("SDK archive has an unsafe member")
            source.extractall(destination)
    else:
        with tarfile.open(archive) as source:
            source.extractall(destination, filter="data")


def verify(directory, spec, target):
    source = spec["targets"][target]
    if inventory_digest(inventory(directory)) != source["inventorySha256"]:
        raise ValueError("Installed JDK differs from the complete vendor archive inventory")
    home = directory / source["home"]
    if not home.resolve().is_relative_to(directory.resolve()):
        raise ValueError("JDK home leaves its installation")
    for name in ("LICENSE", "ADDITIONAL_LICENSE_INFO", "ASSEMBLY_EXCEPTION"):
        if not (home / "legal/java.base" / name).is_file():
            raise ValueError("Developer JDK legal notices are missing")
    suffix = ".exe" if target == "windows-x64" else ""
    environment = java_environment()
    actual = subprocess.check_output([str(home / ("bin/javac" + suffix)), "--version"], env=environment, text=True, stderr=subprocess.STDOUT).strip()
    if actual != spec["javacVersion"]:
        raise ValueError("Developer javac differs from its exact version pin")
    return home


def provision(spec, target, directory, archive=None):
    source = spec["targets"][target]
    url = urllib.parse.urlsplit(source["url"])
    if (url.scheme != "https" or url.hostname != "github.com" or url.username or url.password or url.query or url.fragment
            or not url.path.startswith("/adoptium/temurin21-binaries/releases/download/")
            or not re.fullmatch(r"[0-9a-f]{64}", source["sha256"])):
        raise ValueError("JDK needs the pinned official vendor source and checksum")
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / ("temurin-" + spec["version"] + "-" + target)
    if destination.exists():
        return verify(destination, spec, target)
    with tempfile.TemporaryDirectory(prefix="jdk-provision-", dir=directory) as temporary:
        work = Path(temporary)
        if archive is None:
            archive = work / "vendor.archive"
            urllib.request.urlretrieve(source["url"], archive)
        archive = Path(archive)
        if sha(archive) != source["sha256"]:
            raise ValueError("Developer JDK archive checksum mismatch")
        unpacked = work / "sdk"
        unpacked.mkdir()
        extract(archive, unpacked)
        verify(unpacked, spec, target)
        unpacked.rename(destination)
    return destination / source["home"]


def home(root=ROOT):
    spec = json.loads((root / "tools/jvm/toolchains.json").read_text())
    target = current_target()
    directory = root / ".local/toolchains" / ("temurin-" + spec["version"] + "-" + target)
    return verify(directory, spec, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provision", action="store_true")
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    spec = json.loads((ROOT / "tools/jvm/toolchains.json").read_text())
    target = current_target()
    if args.archive and not args.provision:
        raise ValueError("A local vendor archive requires explicit provisioning")
    if args.provision:
        provision(spec, target, ROOT / ".local/toolchains", args.archive)
    else:
        home()
    print("Temurin JDK " + spec["version"] + " / " + target)


if __name__ == "__main__":
    main()
