"""Preserve the native renderer's original sources and isolate header ownership."""

import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/dependencies"))
from source_files import archive_bytes, digest, encoded, member, read_snapshot


SCOPE = b"""SyncWatch native objects source profile
Original upstream sources and grants are preserved without patches.
GN and platform headers are generated from the retained original templates.
The selected Linux profile excludes RAW photographic DNG/PIEX decoding.
Movie formats belong to VLC; text, SVG, PNG, JPEG and WebP remain enabled.
This package contains native objects, static archives and a source-built build tool.
It does not contain a qualified linked Skiko runtime or a desktop application.
Platform clients, fonts, runtime packaging, native video and visible acceptance
remain independent requirements. It does not establish physical synchronization.
"""


def validate(profile):
    if (profile["schemaVersion"] != 1 or profile["profile"] != "linux-native-objects-v1"
            or profile["target"] != "linux-x64" or profile["nativeRuntimeQualified"] is not False):
        raise ValueError("Unknown or prematurely qualified native object profile")
    occupied = set()
    paths = set()
    for name, source in profile["sources"].items():
        if (not re.fullmatch(r"[a-z][a-z0-9-]+", name)
                or not re.fullmatch(r"3rdparty/[a-z][a-z0-9-]+", source["path"])
                or source["path"] in paths or not re.fullmatch(r"[0-9a-f]{40}", source["revision"])
                or not source["license"] or not source["notices"]):
            raise ValueError("Native source needs a unique pinned submodule and original grants")
        paths.add(source["path"])
        member(source["stage"])
        if (source["exports"] != sorted(source["files"])
                or not set(source["notices"]) <= source["files"].keys()
                or not set(source["executables"]) <= source["files"].keys()):
            raise ValueError("Native source/export/grant inventory is incomplete")
        for filename, pin in source["files"].items():
            member(filename)
            if not re.fullmatch(r"[0-9a-f]{64}", pin):
                raise ValueError("Native source requires an exact content digest")
            destination = (Path(source["stage"]) / filename).as_posix()
            if destination.casefold() in occupied:
                raise ValueError("Native source staging would overwrite another owner")
            occupied.add(destination.casefold())
    if (any("dng_sdk" in s["stage"] or "/piex" in s["stage"] for s in profile["sources"].values())
            or "skia_use_dng_sdk=false" not in profile["gnArguments"]
            or "skia_use_piex=false" not in profile["gnArguments"]):
        raise ValueError("RAW photographic decoders are outside the reviewed native profile")
    return profile


def profile_data():
    return validate(json.loads((ROOT / "tools/desktop/profile.json").read_text()))


def jni_units(profile):
    return sorted(name for name in profile["sources"]["skiko"]["files"] if name.endswith((".cc", ".cpp"))
                  and any(name.startswith(root + "/") for root in profile["jni"]["sourceRoots"]))


def snapshots(directory, profile, *, archive=False):
    return {name: read_snapshot(directory / (Path(source["path"]).name + ".tar" if archive else source["path"]), source)
            for name, source in profile["sources"].items()}


def materialize(directory, originals, profile):
    trees = {}
    for name, source in profile["sources"].items():
        target = directory / source["stage"]
        trees[name] = target
        for filename, data in originals[name].items():
            path = target / filename
            if path.exists() or path.is_symlink():
                raise ValueError("Native source staging requires an empty owned tree")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o755 if filename in source["executables"] else 0o644)
            os.utime(path, (profile["sourceDateEpoch"], profile["sourceDateEpoch"]))
    return trees


def legal_files(originals, profile):
    files = {"SCOPE.txt": SCOPE}
    for name, source in profile["sources"].items():
        for path in source["notices"]:
            files["notices/" + name + "/" + path] = originals[name][path]
    files["THIRD-PARTY-NOTICES.txt"] = ("Original native source grants\n\n"
        "This software uses the FreeType Project (www.freetype.org).\n"
        "This software is based in part on the work of the Independent JPEG Group.\n\n" + "".join(
        name + " — " + source["license"] + "\n" + "\n".join("notices/" + name + "/" + path for path in source["notices"]) + "\n\n"
        for name, source in profile["sources"].items())).encode()
    return files


def source_archive(originals, profile, generated):
    return archive_bytes({"profile.json": encoded(profile), "SCOPE.txt": SCOPE,
                          **{"originals/" + name + "/" + path: data for name, files in originals.items() for path, data in files.items()},
                          **{"generated/" + path: data for path, data in generated.items()}})
