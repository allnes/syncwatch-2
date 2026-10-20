"""Package exact startup declarations and verify a fresh developer-SDK isolation probe."""

import argparse
import json
import os
from pathlib import Path
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dependencies"))
from source_files import archive_bytes, digest, encoded, read_snapshot
from sdk_probe import probe
from source_analysis import analyze


ROOT = Path(__file__).resolve().parents[2]
COMPONENT = "cpython-startup-sources"
SUMMARY = ("SyncWatch source-reference selection: six original CPython startup declaration/reference files, "
           "unchanged. No interpreter implementation or standard library is included. "
           "First-party analysis, proposed startup policy and developer-SDK probe are separate additions. "
           "No CPython source file was modified. No native runtime or embedding ABI was built or verified.\n").encode()


def profile_data():
    profile = json.loads((ROOT / "tools/python-runtime/profile.json").read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "tools/dependencies/components.json").read_text(encoding="utf-8"))["components"]
    specification = {key: profile["source"][key] for key in ("revision", "license", "notices", "exports")}
    specification.update(requires=[], unusedSubmodules={})
    if (profile["schemaVersion"] != 1 or profile["runtimeReady"] is not False
            or set(profile["source"]["files"]) != set(profile["source"]["exports"])
            or registry[COMPONENT]["sources"] != {profile["source"]["path"]: specification}
            or registry[COMPONENT]["roots"] != [profile["source"]["path"]]
            or registry["syncplay-runtime"]["status"] != "unavailable"):
        raise ValueError("Startup source profile differs from the registered non-executable source graph")
    return profile


def payload_files(files, profile):
    analysis = encoded(analyze(files, profile))
    if digest(analysis) != profile["analysisSha256"]:
        raise ValueError("Startup declaration analysis differs from the reviewed profile")
    archive = archive_bytes(files)
    if digest(archive) != profile["sourceArchiveSha256"]:
        raise ValueError("Unchanged startup source archive differs")
    result = {"sources.zip": archive, "source-analysis.json": analysis, "SELECTION.txt": SUMMARY,
              "sdk-isolation.json": encoded(probe()),
              "source-manifest.json": encoded({"schemaVersion": 1, "source": profile["source"],
                                               "sourceArchiveSha256": digest(archive),
                                               "analysisSha256": digest(analysis), "runtimeReady": False,
                                               "nativeRuntimeBuilt": False, "embeddingAbiVerified": False})}
    for name in profile["source"]["notices"]:
        result["notices/cpython/" + name] = files[name]
    return result


def verify(payload, expected):
    found = set()
    for entry in payload.rglob("*"):
        if entry.is_symlink():
            raise ValueError("Startup payload must not contain symbolic links")
        if entry.is_file():
            name = entry.relative_to(payload).as_posix()
            found.add(name)
            if name not in expected or entry.read_bytes() != expected[name]:
                raise ValueError("Startup payload, full notice or selection summary differs: " + name)
    if found != set(expected):
        raise ValueError("Startup payload has missing or unexpected files")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "verify"))
    parser.add_argument("--platform", choices=("linux-x64", "macos-arm64", "windows-x64"))
    args = parser.parse_args()
    profile = profile_data()
    if args.operation == "build":
        if json.loads(os.environ["SYNCWATCH_DEPENDENCY_FLAGS"]) != {"profile": "isolated-startup-sources-v1", "version": profile["version"]}:
            raise ValueError("Unknown startup source build profile")
        snapshot = Path(os.environ["SYNCWATCH_DEPENDENCY_SOURCES"]) / profile["source"]["path"]
        payload = Path(os.environ["SYNCWATCH_DEPENDENCY_OUTPUT"])
    else:
        target = args.platform or {("Darwin", "arm64"): "macos-arm64", ("Linux", "x86_64"): "linux-x64", ("Windows", "AMD64"): "windows-x64"}[(platform.system(), platform.machine())]
        directory = ROOT / "artifacts/dependencies" / COMPONENT / target
        snapshot, payload = directory / "cpython.tar", directory / "payload"
    expected = payload_files(read_snapshot(snapshot, profile["source"]), profile)
    if args.operation == "build":
        for name, data in expected.items():
            target = payload / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    verify(payload, expected)
    print(json.dumps({"component": COMPONENT, "sourceFiles": len(profile["source"]["files"]),
                      "sourceArchiveSha256": profile["sourceArchiveSha256"], "runtimeReady": False,
                      "nativeRuntimeBuilt": False, "embeddingAbiVerified": False}, sort_keys=True))


if __name__ == "__main__":
    main()
