"""Validate the exact headless engine dependency and original-notice identities."""

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def graph_data():
    value = json.loads((Path(__file__).with_name("graph.json")).read_text(encoding="utf-8"))
    if (value["schemaVersion"] != 1 or value["profile"] != "headless-syncplay-tls-v1"
            or value["runtimeReady"] is not False
            or set(value["targets"]) != {"macos-arm64", "windows-x64", "linux-x64"}):
        raise ValueError("Unknown headless runtime graph")
    sources = value["sources"]
    for crate in value["crates"]:
        if crate["source"] not in sources or not crate["name"] or not crate["version"]:
            raise ValueError("Rust crate has no declared original source")
        path = Path(crate["path"])
        if path.is_absolute() or ".." in path.parts or "\\" in crate["path"]:
            raise ValueError("Rust crate path leaves its original repository")
    if len({c["name"] for c in value["crates"]}) != len(value["crates"]):
        raise ValueError("Ambiguous Rust crate authority")
    return value


def check_originals(root=ROOT):
    graph = graph_data()
    entries = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=root)
    index = {}
    for record in entries.split(b"\0"):
        if record:
            metadata, path = record.decode().split("\t")
            mode, revision, stage = metadata.split()
            index[path] = mode, revision, stage
    checked = 0
    for source in graph["sources"].values():
        if index.get(source["path"]) != ("160000", source["revision"], "0"):
            raise ValueError("Runtime source differs from the Git submodule pin: " + source["path"])
        repository = root / source["path"]
        if not source["noticeSha256"]:
            raise ValueError("Source has no complete original notice inventory: " + source["path"])
        for name, expected in source["noticeSha256"].items():
            data = subprocess.check_output(["git", "show", source["revision"] + ":" + name], cwd=repository)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError("Original complete notice differs: " + source["path"] + "/" + name)
            checked += 1
    return {"sourceRoots": len(graph["sources"]), "rustCrates": len(graph["crates"]),
            "originalNotices": checked, "runtimeReady": False}


if __name__ == "__main__":
    print(json.dumps(check_originals(), sort_keys=True))
