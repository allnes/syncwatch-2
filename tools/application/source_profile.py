"""Validate application runtime sources against the repository's indexed Gitlinks."""

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/dependencies"))
import build as dependencies


def read(path, root=ROOT):
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    if profile.get("schemaVersion") != 1 or profile.get("target") != "linux-x64":
        raise ValueError("Application source profile requires its declared schema and native target")
    sources = profile.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("Application runtime requires an explicit source graph")
    pins = dependencies.index(root)
    for name, source in sources.items():
        required = {"path", "revision", "tree", "license", "notices", "exports", "archiveSha256"}
        if (not re.fullmatch(r"[a-z][a-z0-9-]*", name)
                or not isinstance(source, dict) or set(source) not in (required, required | {"archiveFormat"})
                or source["path"] != "3rdparty/" + name
                or not re.fullmatch(r"[0-9a-f]{40}", source["revision"])
                or not re.fullmatch(r"[0-9a-f]{40}", source["tree"])
                or not re.fullmatch(r"[0-9a-f]{64}", source["archiveSha256"])
                or pins.get(source["path"]) != ("160000", source["revision"])
                or not isinstance(source["license"], str) or not source["license"].strip()
                or not isinstance(source["notices"], list) or not source["notices"]
                or source.get("archiveFormat", "tar.gz") not in {"tar", "tar.gz"}):
            raise ValueError("Application source differs from its indexed Gitlink or original source policy")
        # Reuse the dependency export boundary, including notice coverage and portable paths.
        dependencies.export_paths(source)
    if "moduleRoots" in profile:
        modules = profile["moduleRoots"]
        if (not isinstance(modules, list) or not modules or len(set(modules)) != len(modules)
                or any(not isinstance(name, str) or not re.fullmatch(r"(?:java|jdk)\.[a-z0-9.]+", name) for name in modules)
                or "openjdk" not in sources or "Makefile" not in sources["openjdk"]["exports"]
                or not {"LICENSE", "ADDITIONAL_LICENSE_INFO", "ASSEMBLY_EXCEPTION"}.issubset(sources["openjdk"]["notices"])):
            raise ValueError("Application JVM profile omits module roots, original build entry or root grants")
    else:
        order = profile.get("buildOrder")
        libraries = profile.get("runtimeLibraries")
        if (not isinstance(order, list) or len(order) != len(sources) or set(order) != set(sources)
                or not isinstance(libraries, list) or not libraries or len(set(libraries)) != len(libraries)
                or any(not isinstance(name, str) or not re.fullmatch(r"lib[A-Za-z0-9]+\.so\.[0-9]+", name) for name in libraries)):
            raise ValueError("Dynamic client profile requires an exact build order and runtime library names")
    return profile
