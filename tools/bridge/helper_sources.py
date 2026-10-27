"""Shared first-party input inventory for native helper producers and consumers."""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Helper inputs must not contain aliases")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = digest(path)
    return result


def first_party_inputs(root=ROOT):
    directories = ["packages/ipc", "packages/syncplay-helper", "packages/python-startup", "contracts", "tools/bridge"]
    return {directory + "/" + name: value for directory in directories
            for name, value in inventory(root / directory).items()
            if "__pycache__" not in name.split("/") and not name.endswith(".pyc")}
