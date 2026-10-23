"""Verify original pinned media sources and materialize isolated build inputs."""

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/dependencies"))
from source_files import digest, read_snapshot


def profile_data():
    profile = json.loads((ROOT / "tools/vlc/profile.json").read_text())
    if profile["schemaVersion"] != 1 or profile["profile"] != "native-decoder-v1":
        raise ValueError("Unknown native media profile")
    for source in profile["sources"].values():
        if (source["exports"] != sorted(set(source["exports"])) or
                not set(source["notices"]) <= set(source["files"]) or
                not set(source["executables"]) <= set(source["files"])):
            raise ValueError("Media source/grant inventory is incomplete")
    component = json.loads((ROOT / "tools/dependencies/components.json").read_bytes())["components"]["libvlc"]
    expected = {source["path"]: {key: source[key] for key in
                ["revision", "license", "notices", "exports", "requires", "unusedSubmodules"]}
                for source in profile["sources"].values()}
    if component.get("status") != "ready" or component.get("sources") != expected:
        raise ValueError("Registered media source graph differs from the reviewed build profile")
    return profile


def snapshots(directory, profile):
    return {name: read_snapshot(directory / source["path"], source)
            for name, source in profile["sources"].items()}


def selected_plugins(profile, target):
    return sorted(set(profile["plugins"] + profile.get("platformPlugins", {}).get(target, [])))


def materialize(directory, files, source, epoch):
    for name, data in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o755 if name in source["executables"] else 0o644)
        os.utime(path, (epoch, epoch))


def restore_iconv(directory):
    """Remove exactly the mirror's pinned MSVC changes, then verify GNU originals."""
    expected = json.loads((ROOT / "tools/vlc/iconv-original.json").read_text())["files"]
    # A disposable Git root scopes the patch paths independently of the checkout.
    subprocess.run(["git", "init", "-q", str(directory)], check=True)
    for arguments in [["--reverse", "--check"], ["--reverse"]]:
        subprocess.run(["git", "-C", str(directory), "-c", "core.autocrlf=false", "apply", *arguments,
                        str(directory / "libiconv.diff")], check=True)
    files = {p.relative_to(directory / "source").as_posix(): digest(p.read_bytes())
             for p in (directory / "source").rglob("*") if p.is_file()}
    if files != expected:
        raise ValueError("Restored libiconv differs from the complete original GNU release")
    return directory / "source"
