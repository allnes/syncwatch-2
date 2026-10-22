"""Explicitly provision a native Windows Perl build SDK when none is installed."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile


def resolve():
    if os.name != "nt":
        return
    candidate = shutil.which("perl")
    if candidate and subprocess.check_output([candidate, "-e", 'print "$^O"'], text=True) == "MSWin32":
        print(json.dumps({"nativePerlInstalled": True})); return
    home = Path.home() / ".local/share/syncwatch/toolchains/strawberry-perl-5.42.3.1"
    if not home.exists():
        home.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="perl-sdk-", dir=home.parent) as temporary:
            work = Path(temporary)
            archive = work / "vendor.zip"
            urllib.request.urlretrieve("https://github.com/StrawberryPerl/Perl-Dist-Strawberry/releases/download/SP_54231_64bit/strawberry-perl-5.42.3.1-64bit-portable.zip", archive)
            with archive.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != "6a081a811781c30aca51dbc036afd93092af91e3297901f02c17043795a10690":
                    raise ValueError("Perl SDK vendor archive checksum differs")
            with zipfile.ZipFile(archive) as package:
                for entry in package.infolist():
                    name = PurePosixPath(entry.filename)
                    if name.is_absolute() or ".." in name.parts or ":" in entry.filename or "\\" in entry.filename:
                        raise ValueError("Unsafe Perl SDK member")
                package.extractall(work / "original")
            work.rename(home)
    perl = home / "original/perl/bin/perl.exe"
    version = subprocess.check_output([str(perl), "-e", 'print "$^V $^O"'], text=True)
    if version != "v5.42.3 MSWin32":
        raise ValueError("Native Perl SDK version differs")
    print(json.dumps({"nativePerlInstalled": True, "version": version}))


if __name__ == "__main__":
    resolve()
