"""Exact original bootstrap encoding source and its explicitly limited imports."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = "cpython-bootstrap-stdlib"


def profile_data():
    profile = json.loads((ROOT / "tools/python-stdlib/profile.json").read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "tools/dependencies/components.json").read_text(encoding="utf-8"))["components"]
    source = profile["source"]
    expected = {key: source[key] for key in ("revision", "license", "notices", "exports")}
    expected.update(requires=[], unusedSubmodules={})
    modules = {"Lib/encodings/" + name + ".py" for name in ["__init__", "aliases", *profile["codecs"]]}
    if (profile["schemaVersion"] != 1 or profile["runtimeReady"] is not False
            or source["exports"] != sorted(source["files"])
            or set(source["files"]) != modules | set(source["notices"])
            or set(profile["vectors"]) != set(profile["codecs"])
            or registry[COMPONENT]["roots"] != [source["path"]]
            or registry[COMPONENT]["sources"] != {source["path"]: expected}
            or registry["syncplay-runtime"]["status"] != "unavailable"):
        raise ValueError("Bootstrap stdlib profile differs from its non-runtime source graph")
    return profile


def analyze(files, profile):
    imports = {}
    for name, data in sorted(files.items()):
        if not name.endswith(".py"):
            continue
        tree = ast.parse(data, filename=name)
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                found.add("." * node.level + (node.module or "") + ":" + ",".join(a.name for a in node.names))
        if not found <= {"codecs", "sys", "_winapi", "encodings.mbcs", ".:aliases"}:
            raise ValueError("Bootstrap codec imports an unreviewed interface: " + name)
        imports[name] = sorted(found)
    aliases_tree = ast.parse(files["Lib/encodings/aliases.py"])
    aliases = ast.literal_eval(next(node.value for node in aliases_tree.body if isinstance(node, ast.Assign)))
    selected = {name: target for name, target in sorted(aliases.items()) if target in profile["codecs"]}
    return {"schemaVersion": 1, "imports": imports, "codecs": profile["codecs"], "selectedAliases": selected,
            "requiredCoreInterfaces": profile["requiredCoreInterfaces"],
            "windowsOptionalInterface": profile["windowsOptionalInterface"],
            "unsupportedExamples": profile["unsupportedExamples"], "runtimeReady": False,
            "scope": "Exact encoding Python sources only; core/frozen interfaces are not distributed or cleared here."}
