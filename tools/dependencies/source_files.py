"""Exact source snapshots and deterministic unchanged-source archives."""

import hashlib
import io
import json
from pathlib import PurePosixPath
import tarfile
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def member(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or str(path) != name or any(p in {".", ".."} for p in path.parts)
            or any(c in name for c in ("\\", ":", "\x00"))):
        raise ValueError("Unsafe source snapshot member")


def read_snapshot(path, specification):
    files = {}
    if path.is_symlink():
        raise ValueError("Source snapshot must not be a symbolic link")
    if path.is_dir():
        for entry in path.rglob("*"):
            if entry.is_symlink():
                raise ValueError("Source snapshot requires regular files")
            if entry.is_file():
                name = entry.relative_to(path).as_posix()
                member(name)
                files[name] = entry.read_bytes()
    else:
        with tarfile.open(path) as archive:
            if archive.pax_headers.get("comment") != specification["revision"]:
                raise ValueError("Source snapshot has a different Git revision")
            for entry in archive:
                member(entry.name)
                if entry.isdir():
                    continue
                if not entry.isfile() or entry.name in files:
                    raise ValueError("Source snapshot requires unique regular files")
                files[entry.name] = archive.extractfile(entry).read()
    if set(files) != set(specification["files"]):
        raise ValueError("Source snapshot differs from the exact file inventory")
    for name, data in files.items():
        if digest(data) != specification["files"][name]:
            raise ValueError("Source or notice digest changed: " + name)
    return files


def archive_bytes(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            member(name)
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return stream.getvalue()
