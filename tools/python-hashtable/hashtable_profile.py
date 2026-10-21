"""Exact source/notice inventory and narrowly enabled hashtable provenance graph."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = "cpython-hashtable"
sys.path.insert(0, str(ROOT / "tools/dependencies"))
from source_files import archive_bytes, digest, encoded, read_snapshot
from native_hashtable import fragments


def profile_data():
    profile = json.loads((ROOT / "tools/python-hashtable/profile.json").read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "tools/dependencies/components.json").read_text(encoding="utf-8"))["components"]
    sources = {}
    for source in profile["sources"].values():
        if source["exports"] != sorted(source["files"]):
            raise ValueError("hashtable exports differ from the exact source inventory")
        sources[source["path"]] = {k: source[k] for k in ("revision", "license", "notices", "exports")}
        sources[source["path"]].update(requires=[], unusedSubmodules={})
    if (profile["schemaVersion"] != 1 or profile["runtimeReady"] is not False
            or registry[COMPONENT]["sources"] != sources or registry[COMPONENT]["roots"] != list(sources)
            or registry["syncplay-runtime"]["status"] != "unavailable"):
        raise ValueError("hashtable profile differs from its non-runtime source graph")
    return profile


def read_sources(paths, profile):
    return {name: read_snapshot(paths[name], source) for name, source in profile["sources"].items()}


def original_archive(sources):
    return archive_bytes({origin + "/" + name: data for origin, files in sources.items() for name, data in files.items()})


def analyze(sources):
    def normalize(data):
        return b" ".join(data.replace(b"*", b" ").split())
    original = normalize(sources["libcfu"]["COPYING"])
    for origin, name in [("cpython", "Python/hashtable.c"), ("libcfu", "src/cfuhash.c"), ("libcfu", "src/cfuhash.h")]:
        # The original libcfu C headers add one period after the holder name.
        expected = original if origin == "cpython" else original.replace(b"Don Owens All", b"Don Owens. All")
        if expected not in normalize(sources[origin][name]):
            raise ValueError("Missing or changed complete cfuhash origin notice")
    pieces = fragments(sources["cpython"])
    return {"schemaVersion": 1, "originalFragmentSha256": {name: digest(data) for name, data in pieces.items()},
            "normalizedBsdNoticeSha256": digest(original), "originalSourcesUnchanged": True,
            "originReferenceCompiled": False, "sourceConfiguration": {"sizeBits": 64, "assertionsEnabled": True},
            "compiledImplementation": "Complete original CPython hashtable declarations and body, exact raw pointer hash/types/macro.",
            "existingOriginModifications": "CPython's original cfuhash-derived implementation remains unchanged.",
            "allocatorPorts": "Explicit first-party standalone ISO C malloc/free, not interpreter allocation/lifecycle.",
            "excluded": ["original libcfu runtime", "interpreter allocator/thread lifecycle", "other CPython core modules"],
            "pinnedEmbeddingAbiVerified": False, "runtimeReady": False}


def validate(sources, profile):
    for origin, source in profile["sources"].items():
        if {name: digest(data) for name, data in sources[origin].items()} != source["files"]:
            raise ValueError("hashtable original source or full notice differs")
    if digest(original_archive(sources)) != profile["sourceArchiveSha256"]:
        raise ValueError("hashtable original source archive differs")
    if digest(encoded(analyze(sources))) != profile["analysisSha256"]:
        raise ValueError("hashtable source/notice/fragment analysis differs")
