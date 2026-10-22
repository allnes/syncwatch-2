"""Explicit CI provisioning of build tools, outside the offline runtime recipe."""

import os
from pathlib import Path
import platform
import subprocess
import sys


def provision():
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["brew", "install", "m4", "autoconf", "automake", "libtool"],
                       env=dict(os.environ, HOMEBREW_NO_AUTO_UPDATE="1"), check=True)
    elif system == "Linux":
        subprocess.run(["sudo", "-n", "apt-get", "update", "-o", "Acquire::Retries=3"], check=True)
        subprocess.run(["sudo", "-n", "apt-get", "install", "--yes", "m4", "autoconf", "automake",
                        "libtool", "libltdl-dev"], check=True)
    directory = Path(__file__).resolve().parent
    subprocess.run([sys.executable, str(directory / "toolchains.py"), "--provision"], check=True)
    subprocess.run([sys.executable, str(directory / "perl_sdk.py")], check=True)


if __name__ == "__main__":
    provision()
