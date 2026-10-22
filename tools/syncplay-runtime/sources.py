"""Materialize only verified original build inputs, keeping derivatives separate."""

import json
from pathlib import Path
import sys

from source_graph import ROOT, graph_data

sys.path.insert(0, str(ROOT / "tools/dependencies"))
from source_files import read_snapshot
sys.path.insert(0, str(ROOT / "tools/python-build"))
from source_profile import materialize


def specifications():
    data = json.loads(Path(__file__).with_name("sources.json").read_text(encoding="utf-8"))
    graph = graph_data()
    if (data["schemaVersion"] != 1 or data["profile"] != graph["profile"]
            or set(data["sources"]) != set(graph["sources"])):
        raise ValueError("Runtime source inventory differs from its graph")
    for name, source in data["sources"].items():
        authority = graph["sources"][name]
        if any(source[k] != authority[k] for k in ["path", "revision", "license"]):
            raise ValueError("Runtime source authority differs")
        if {n: source["files"][n] for n in source["notices"]} != authority["noticeSha256"]:
            raise ValueError("Runtime original grant inventory differs")
    return data["sources"]


def read_sources(paths):
    return {name: read_snapshot(paths[name], source) for name, source in specifications().items()}


def materialize_sources(destination, sources):
    result = {}
    for name, specification in specifications().items():
        path = destination / Path(specification["path"]).name
        materialize(path, sources[name], specification["executables"])
        result[name] = path
    return result
