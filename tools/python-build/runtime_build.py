"""Build or verify source-pinned embedded CPython on its native target."""

import argparse
import json
import os
from pathlib import Path
import tempfile

from native_build import build_native, sdk_identity
from runtime_package import package, verify
from source_profile import COMPONENT, ROOT, profile_data, read_sources, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "verify", "sdk"))
    parser.add_argument("--platform", choices=("macos-arm64", "windows-x64", "linux-x64"))
    args = parser.parse_args()
    cmake, options, sdk = sdk_identity()
    if args.operation == "sdk":
        print(json.dumps(sdk, sort_keys=True)); return
    if args.platform and args.platform != sdk["target"]:
        raise ValueError("Embedded runtime requires its native target")
    profile = profile_data()
    if args.operation == "build":
        if json.loads(os.environ["SYNCWATCH_DEPENDENCY_FLAGS"]) != {"profile": profile["profile"]}:
            raise ValueError("Unknown embedded interpreter configuration")
        root = Path(os.environ["SYNCWATCH_DEPENDENCY_SOURCES"])
        paths = {name: root / profile[key]["path"] for name, key in [("cpython", "source"), ("zlib", "zlib")]}
        payload = Path(os.environ["SYNCWATCH_DEPENDENCY_OUTPUT"])
    else:
        root = ROOT / "artifacts/dependencies" / COMPONENT / sdk["target"]
        paths = {name: root / (name + ".tar") for name in ["cpython", "zlib"]}
        payload = root / "payload"
    sources = read_sources(paths, profile)
    validate(sources, profile)
    if args.operation == "build":
        with tempfile.TemporaryDirectory(prefix="sw-python-build-") as temporary:
            source, native, commands = build_native(Path(temporary).resolve(), sources, profile, cmake, options, sdk)
            package(payload, sources, profile, sdk, source, native, commands, options)
    report = verify(payload, sources, profile, sdk, options)
    print(json.dumps({"component": COMPONENT, "target": sdk["target"], "version": profile["version"],
                      "pinnedRuntimeBuilt": True, "pinnedEmbeddingAbiVerified": True,
                      "cases": report["proof"]["cases"], "syncplayRuntimeReady": False}, sort_keys=True))


if __name__ == "__main__":
    main()
