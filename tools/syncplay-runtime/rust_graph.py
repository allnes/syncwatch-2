"""Bind Cargo's actual enabled packages to the exact audited Git authorities."""

import json
from pathlib import Path
import re
import subprocess

from source_graph import graph_data


def configure(source, paths):
    graph = graph_data()
    manifest = source / "Cargo.toml"
    original = manifest.read_text(encoding="utf-8")
    if "[patch.crates-io]" in original:
        raise ValueError("Original cryptography manifest unexpectedly overrides source authorities")
    overrides = "\n[patch.crates-io]\n" + "".join(
        json.dumps(crate["name"]) + " = { path = " + json.dumps((paths[crate["source"]] / crate["path"]).as_posix()) + " }\n"
        for crate in graph["crates"])
    manifest.write_text("# SyncWatch 2026-10-22: bind enabled crates to pinned original Git sources.\n"
                        + original + overrides, encoding="utf-8", newline="\n")
    # Dependency workspaces contain development-only members. Their package and
    # dependency declarations remain original; unselected workspace members are
    # excluded from this configured build, without changing library algorithms.
    for path in set(paths[c["source"]] for c in graph["crates"]):
        manifest = path / "Cargo.toml"
        original = manifest.read_text(encoding="utf-8")
        changed = re.sub(r"(?ms)^(?:members|default-members)\s*=\s*\[.*?\]\s*", "", original)
        if changed != original:
            manifest.write_text("# SyncWatch 2026-10-22: exclude development workspace members.\n" + changed,
                                encoding="utf-8", newline="\n")


def verify_metadata(cargo, source, paths, environment):
    data = json.loads(subprocess.check_output([str(cargo), "metadata", "--offline", "--format-version", "1"],
        cwd=source, env=environment, stderr=subprocess.PIPE, timeout=120))
    graph = graph_data()
    expected = {c["name"]: (c["version"], (paths[c["source"]] / c["path"] / "Cargo.toml").resolve())
                for c in graph["crates"]}
    found = {}
    for package in data["packages"]:
        path = Path(package["manifest_path"]).resolve()
        if package["source"] is not None:
            raise ValueError("Cargo resolved an external registry or Git dependency")
        if path.is_relative_to(source.resolve()):
            if not package["name"].startswith("cryptography-"):
                raise ValueError("Unknown cryptography workspace package")
            continue
        identity = package["version"], path
        if package["name"] not in expected or identity != expected[package["name"]]:
            raise ValueError("Cargo selected an undeclared original source: " + package["name"])
        found[package["name"]] = identity
    if found != expected:
        raise ValueError("Cargo omitted a declared enabled crate authority")
    return {name: {"version": version, "source": next(c["source"] for c in graph["crates"] if c["name"] == name)}
            for name, (version, _path) in sorted(found.items())}
