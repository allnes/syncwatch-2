"""Provision explicit developer tools before the offline native media build."""

import hashlib
import json
import lzma
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import tarfile
import tempfile
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


def unpack_windows_base(archive, directory):
    with tarfile.open(archive) as package:
        for item in package:
            if not (item.name == "msys64" or item.name.startswith("msys64/")) or ".." in Path(item.name).parts:
                raise ValueError("Unsafe developer SDK archive member")
    # Python already decodes the verified xz archive above. Do not require an
    # ambient xz executable when the bootstrap tar runs from a native shell.
    with tempfile.TemporaryDirectory(prefix="base-", dir=directory) as temporary:
        unpacked = Path(temporary) / "msys2-base.tar"
        with lzma.open(archive, "rb") as source, unpacked.open("wb") as destination:
            shutil.copyfileobj(source, destination)
        bootstrap = Path("C:/msys64/usr/bin/tar.exe")
        subprocess.run([str(bootstrap), "--force-local", "-xf", unpacked.as_posix(),
                        "-C", directory.as_posix(), "--no-same-owner"], check=True)


def windows():
    if os.environ.get("SYNCWATCH_VLC_MSYS_ROOT"):
        return
    profile = json.loads((ROOT / "tools/vlc/windows-sdk.json").read_bytes())
    directory = ROOT / ".local/vlc-sdk/windows"
    root = directory / "msys64"
    archive = directory / "base.tar.xz"
    download(profile["base"], archive)
    if not root.exists():
        unpack_windows_base(archive, directory)
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
        network = ["-o", "Acquire::Retries=2", "-o", "Acquire::http::Timeout=30",
                   "-o", "Acquire::https::Timeout=30", "-o", "DPkg::Lock::Timeout=60"]
        # The privileged timeout owns apt's process group, including download workers.
        # Bound metadata refresh without interrupting package installation/configuration.
        subprocess.run(["sudo", "-n", "timeout", "--verbose", "--signal=TERM", "--kill-after=10s", "300s",
                        "apt-get", *network, "update"], check=True, timeout=330)
        subprocess.run(["sudo", "-n", "apt-get", *network, "install", "--yes", "m4", "autoconf", "automake",
                        "autotools-dev", "libtool", "libtool-bin", "gettext", "autopoint", "bison", "flex",
                        "gperf", "pkgconf", "ninja-build", "cmake", "nasm", "patchelf"], check=True)
    elif system == "Windows":
        windows()
    else:
        raise ValueError("Unsupported native media developer host")


if __name__ == "__main__":
    main()
