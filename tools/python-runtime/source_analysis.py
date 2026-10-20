"""Inspect selected pinned declarations, without preprocessing C or inferring ABI."""

import re


def uncomment(data):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", data.decode("utf-8"), flags=re.S)


def normalized(text):
    return re.sub(r"\s*([*(),])\s*", r"\1", " ".join(text.split()))


def analyze(files, profile):
    version = re.findall(r'^\s*#define\s+PY_VERSION\s+"([^"]+)"\s*$', uncomment(files["Include/patchlevel.h"]), re.M)
    if version != [profile["version"]]:
        raise ValueError("CPython version declaration differs")
    header = uncomment(files["Include/cpython/initconfig.h"])
    fields = {}
    policy = profile["startupPolicy"]
    for name, overrides in [("PyPreConfig", policy["preConfig"]), ("PyConfig", policy["config"])]:
        if overrides.get("isolated") != 1 or overrides.get("use_environment") != 0 or overrides.get("parse_argv") != 0:
            raise ValueError("Startup policy must isolate environment and arguments")
        if any(type(value) is not int or value not in (0, 1) for value in overrides.values()):
            raise ValueError("Startup overrides must be boolean integers")
        bodies = re.findall(r"typedef\s+struct\s+" + name + r"\s*\{([^{}]*)\}\s*" + name + r"\s*;", header, re.S)
        if len(bodies) != 1:
            raise ValueError("Missing or duplicate configuration structure: " + name)
        required = {field: "int" for field in overrides}
        if name == "PyConfig":
            required.update({field: "wchar_t*" for field in policy["explicitPathFields"]})
            required["module_search_paths"] = "PyWideStringList"
        declarations = [normalized(part) for part in re.sub(r"^\s*#.*$", "", bodies[0], flags=re.M).split(";")]
        for field, kind in required.items():
            expected = normalized(kind + " " + field)
            if declarations.count(expected) != 1:
                raise ValueError("Missing, duplicate or changed startup field: " + name + "." + field)
        fields[name] = required
    functions = {}
    for path, expected in profile["requiredFunctions"].items():
        found = re.findall(r"PyAPI_FUNC\s*\(([^()]*)\)\s*(\w+)\s*\(([^;{}]*)\)\s*;", uncomment(files[path]), re.S)
        for name, signature in expected.items():
            matches = [normalized(result + " " + symbol + "(" + args + ")")
                       for result, symbol, args in found if symbol == name]
            if matches != [signature]:
                raise ValueError("Missing, duplicate or changed startup function: " + name)
            functions[name] = signature
    return {"schemaVersion": 1, "sourceVersion": version[0], "fields": fields, "functions": functions,
            "startupPolicy": policy, "nativeRuntimeBuilt": False, "embeddingAbiVerified": False, "runtimeReady": False}
