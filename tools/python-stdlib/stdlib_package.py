"""Build and freshly verify an unchanged, ZIP-importable bootstrap encoding subset."""

import argparse
import json
import os
from pathlib import Path
import platform
import sys

from stdlib_profile import COMPONENT, ROOT, analyze, profile_data

sys.path.insert(0, str(ROOT / "tools/dependencies"))
from source_files import archive_bytes, digest, encoded, read_snapshot

SUMMARY = ("SyncWatch CPython bootstrap selection: original encoding package/alias data, ASCII, Latin-1, "
           "UTF-8/BOM, UTF-16 and UTF-32 endian variants. Original source bytes and notices are unchanged. "
           "The runtime ZIP removes only the upstream Lib/ path prefix and uses stored entries, without bytecode. "
           "Unselected alias targets remain unavailable. No interpreter, native/frozen module, SDK, complete "
           "standard library, TLS or Syncplay runtime is included. Analysis and inventory are first-party additions.\n").encode()


def payload_files(files, profile):
    archive = archive_bytes({name.removeprefix("Lib/"): data for name, data in files.items() if name.startswith("Lib/")})
    sources = archive_bytes(files)
    analysis = encoded(analyze(files, profile))
    expected = (profile["stdlibSha256"], profile["sourceArchiveSha256"], profile["analysisSha256"])
    if (digest(archive), digest(sources), digest(analysis)) != expected:
        raise ValueError("Bootstrap archive or analysis differs from the reviewed source profile")
    manifest = {"schemaVersion": 1, "source": profile["source"], "stdlibSha256": digest(archive),
                "analysisSha256": digest(analysis), "runtimeReady": False, "pinnedRuntimeBuilt": False,
                "entries": {name.removeprefix("Lib/"): {"size": len(data), "sha256": digest(data)}
                            for name, data in sorted(files.items()) if name.startswith("Lib/")}}
    result = {"stdlib.zip": archive, "sources.zip": sources, "source-analysis.json": analysis,
              "source-manifest.json": encoded(manifest), "SELECTION.txt": SUMMARY}
    for name in profile["source"]["notices"]:
        result["notices/cpython/" + name] = files[name]
    return result


def verify(payload, expected):
    if payload.is_symlink():
        raise ValueError("Bootstrap stdlib payload must not contain symbolic links")
    found = set()
    for entry in payload.rglob("*"):
        if entry.is_symlink():
            raise ValueError("Bootstrap stdlib payload must not contain symbolic links")
        if entry.is_file():
            name = entry.relative_to(payload).as_posix()
            if name not in expected or entry.read_bytes() != expected[name]:
                raise ValueError("Bootstrap stdlib archive, inventory or full notice differs: " + name)
            found.add(name)
    if found != set(expected):
        raise ValueError("Bootstrap stdlib payload has missing or unexpected files")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "verify"))
    parser.add_argument("--platform", choices=("linux-x64", "macos-arm64", "windows-x64"))
    args = parser.parse_args()
    profile = profile_data()
    if args.operation == "build":
        if json.loads(os.environ["SYNCWATCH_DEPENDENCY_FLAGS"]) != {"profile": "bootstrap-encodings-v1", "version": profile["version"]}:
            raise ValueError("Unknown bootstrap stdlib build profile")
        snapshot = Path(os.environ["SYNCWATCH_DEPENDENCY_SOURCES"]) / profile["source"]["path"]
        payload = Path(os.environ["SYNCWATCH_DEPENDENCY_OUTPUT"])
    else:
        target = args.platform or {("Darwin", "arm64"): "macos-arm64", ("Linux", "x86_64"): "linux-x64", ("Windows", "AMD64"): "windows-x64"}[(platform.system(), platform.machine())]
        directory = ROOT / "artifacts/dependencies" / COMPONENT / target
        snapshot, payload = directory / "cpython.tar", directory / "payload"
    expected = payload_files(read_snapshot(snapshot, profile["source"]), profile)
    if args.operation == "build":
        for name, data in expected.items():
            path = payload / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    verify(payload, expected)
    print(json.dumps({"component": COMPONENT, "stdlibSha256": profile["stdlibSha256"],
                      "encodingModules": len(profile["codecs"]) + 2, "runtimeReady": False}, sort_keys=True))


if __name__ == "__main__":
    main()
