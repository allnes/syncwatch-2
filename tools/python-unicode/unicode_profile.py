"""Exact enabled source graph for the non-runtime Unicode type-table deliverable."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = "cpython-unicode-types"
sys.path.insert(0, str(ROOT / "tools/dependencies"))
from source_files import archive_bytes, digest, encoded, read_snapshot


def profile_data():
    profile = json.loads((ROOT / "tools/python-unicode/profile.json").read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "tools/dependencies/components.json").read_text(encoding="utf-8"))["components"]
    sources = {}
    for source in profile["sources"].values():
        if source["exports"] != sorted(source["files"]):
            raise ValueError("Unicode exports differ from the exact file inventory")
        sources[source["path"]] = {k: source[k] for k in ("revision", "license", "notices", "exports")}
        sources[source["path"]].update(requires=[], unusedSubmodules={})
    if (profile["schemaVersion"] != 1 or profile["runtimeReady"] is not False
            or registry[COMPONENT]["sources"] != sources or registry[COMPONENT]["roots"] != list(sources)
            or registry["syncplay-runtime"]["status"] != "unavailable"):
        raise ValueError("Unicode profile differs from its non-runtime source graph")
    return profile


def read_sources(paths, profile):
    return {name: read_snapshot(paths[name], source) for name, source in profile["sources"].items()}


def original_archive(sources):
    return archive_bytes({origin + "/" + name: data for origin, files in sources.items() for name, data in files.items()})


def validate(sources, profile):
    for origin, source in profile["sources"].items():
        if {name: digest(data) for name, data in sources[origin].items()} != source["files"]:
            raise ValueError("Unicode original source or full notice differs")
    if digest(original_archive(sources)) != profile["sourceArchiveSha256"]:
        raise ValueError("Unicode original source archive differs")
