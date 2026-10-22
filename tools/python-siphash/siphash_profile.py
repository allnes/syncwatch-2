"""Exact source/notice inventory and narrowly enabled SipHash provenance graph."""

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = "cpython-siphash"
sys.path.insert(0, str(ROOT / "tools/dependencies"))
from source_files import archive_bytes, digest, encoded, read_snapshot
from native_siphash import fragments
from siphash_oracle import source_answers


def profile_data():
    profile = json.loads((ROOT / "tools/python-siphash/profile.json").read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "tools/dependencies/components.json").read_text(encoding="utf-8"))["components"]
    sources = {}
    for source in profile["sources"].values():
        if source["exports"] != sorted(source["files"]):
            raise ValueError("SipHash exports differ from the exact source inventory")
        sources[source["path"]] = {k: source[k] for k in ("revision", "license", "notices", "exports")}
        sources[source["path"]].update(requires=[], unusedSubmodules={})
    if (profile["schemaVersion"] != 1 or profile["runtimeReady"] is not False
            or registry[COMPONENT]["sources"] != sources or registry[COMPONENT]["roots"] != list(sources)):
        raise ValueError("SipHash profile differs from its non-runtime source graph")
    return profile


def read_sources(paths, profile):
    return {name: read_snapshot(paths[name], source) for name, source in profile["sources"].items()}


def original_archive(sources):
    return archive_bytes({origin + "/" + name: data for origin, files in sources.items() for name, data in files.items()})


def analyze(sources):
    notices = []
    for data in (sources["cpython"]["Python/pyhash.c"], sources["csiphash"]["csiphash.c"]):
        matches = re.findall(rb"<MIT License>(.*?)</MIT License>", data, re.S)
        if len(matches) != 1:
            raise ValueError("Missing or ambiguous complete SipHash MIT notice")
        notices.append(b" ".join(matches[0].split()))
    if notices[0] != notices[1] or b"Modified for Python by Christian Heimes:" not in sources["cpython"]["Python/pyhash.c"]:
        raise ValueError("SipHash origin notice or existing modification attribution differs")
    _cases, answers = source_answers(sources)
    pieces = fragments(sources["cpython"])
    return {"schemaVersion": 1, "originalFragmentSha256": {name: digest(data) for name, data in pieces.items()},
            "normalizedMitNoticeSha256": digest(notices[0]), "originalKnownAnswers": answers,
            "originalSourcesUnchanged": True, "originReferenceCompiled": False,
            "compiledFunctions": ["siphash13", "siphash24", "_Py_KeyedHash"],
            "sourceConfiguration": {"littleEndian": True, "sizeBits": 64, "compileSipHash24": True},
            "existingOriginModifications": "Original CPython C89/MSVC/endian handling, memcpy loads and SipHash13 are retained.",
            "excluded": ["full Python hash API", "FNV", "small-string DJBX33A", "numeric/pointer hashes", "runtime entropy"],
            "pinnedEmbeddingAbiVerified": False, "runtimeReady": False}


def validate(sources, profile):
    for origin, source in profile["sources"].items():
        if {name: digest(data) for name, data in sources[origin].items()} != source["files"]:
            raise ValueError("SipHash original source or full notice differs")
    if digest(original_archive(sources)) != profile["sourceArchiveSha256"]:
        raise ValueError("SipHash original source archive differs")
    if digest(encoded(analyze(sources))) != profile["analysisSha256"]:
        raise ValueError("SipHash source/notice/fragment analysis differs")
