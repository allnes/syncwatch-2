"""Provision explicit developer tools before the offline native media build."""

import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def download(item, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        temporary = destination.with_suffix(destination.suffix + ".partial")
        with urllib.request.urlopen(item["url"], timeout=120) as response, temporary.open("wb") as output:
            while data := response.read(1024 * 1024):
                output.write(data)
        temporary.replace(destination)
    with destination.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != item["sha256"]:
        raise ValueError("Developer SDK archive differs from its pinned digest")


def windows():
    if os.environ.get("SYNCWATCH_VLC_MSYS_ROOT"):
        return
    profile = json.loads((ROOT / "tools/vlc/windows-sdk.json").read_bytes())
    directory = ROOT / ".local/vlc-sdk/windows"
    root = directory / "msys64"
    archive = directory / "base.tar.xz"
    download(profile["base"], archive)
    if not root.exists():
        with tarfile.open(archive) as package:
            for item in package:
                if not (item.name == "msys64" or item.name.startswith("msys64/")) or ".." in Path(item.name).parts:
                    raise ValueError("Unsafe developer SDK archive member")
        # The hosted Windows image provides GNU tar as an explicit bootstrap
        # tool. It extracts the independent SDK without changing that installation.
        bootstrap = Path("C:/msys64/usr/bin/tar.exe")
        subprocess.run([str(bootstrap), "--force-local", "-xf", archive.as_posix(),
                        "-C", directory.as_posix(), "--no-same-owner"], check=True)
    packages = directory / "packages"
    for name, item in profile["archives"].items():
        download(item, packages / name)
    env = dict(os.environ, MSYSTEM="UCRT64", MSYS2_PATH_TYPE="minimal", CHERE_INVOKING="1")
    shell = root / "usr/bin/bash.exe"
    subprocess.run([str(shell), "-lc", "true"], env=env, check=True)
    # Archive authenticity is bound to the reviewed SHA256 inventory. Install
    # only these local files; no dependency resolution or mirror refresh occurs.
    config = directory / "pacman-local.conf"
    config.write_bytes(b"[options]\nArchitecture = auto\nSigLevel = Never\n")
    from build_context import shell_path
    command = ["pacman", "--config", shell_path(config), "-U", "--needed", "--noconfirm", "--nodeps",
               *(shell_path(packages / name) for name in profile["archives"])]
    subprocess.run([str(shell), "-lc", shlex.join(command)], env=env, check=True)
    actual = subprocess.check_output([str(shell), "-lc", "pacman -Q"], env=env, text=True).splitlines()
    if actual != profile["installedPackages"]:
        raise ValueError("Provisioned developer SDK differs from its complete pinned package inventory")


def main():
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["brew", "install", "m4", "autoconf", "automake", "libtool", "gettext",
                        "bison", "flex", "gperf", "pkgconf", "ninja", "cmake"],
                       env=dict(os.environ, HOMEBREW_NO_AUTO_UPDATE="1"), check=True)
    elif system == "Linux":
        subprocess.run(["sudo", "-n", "apt-get", "update", "-o", "Acquire::Retries=3"], check=True)
        subprocess.run(["sudo", "-n", "apt-get", "install", "--yes", "m4", "autoconf", "automake",
                        "autotools-dev", "libtool", "libtool-bin", "gettext", "autopoint", "bison", "flex",
                        "gperf", "pkgconf", "ninja-build", "cmake", "nasm", "patchelf"], check=True)
    elif system == "Windows":
        windows()
    else:
        raise ValueError("Unsupported native media developer host")


if __name__ == "__main__":
    main()
