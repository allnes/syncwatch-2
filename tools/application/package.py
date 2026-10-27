"""Build a native development candidate from explicit, already verified runtime inputs."""

import argparse
import importlib
from pathlib import Path
import subprocess
import tempfile

from candidate_tree import assemble
from receipts import ROOT, helper, media, require_host


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=("macos-arm64", "windows-x64", "linux-x64"))
    for name in ("application", "media-package", "helper-package", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    for name in ("bridge", "dotnet", "jvm", "desktop-sdk", "renderer"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--cc", default="cc")
    arguments = parser.parse_args()
    require_host(arguments.target)
    required = {"macos-arm64": (), "windows-x64": ("bridge", "dotnet"),
                "linux-x64": ("bridge", "jvm", "desktop_sdk", "renderer")}[arguments.target]
    if any(getattr(arguments, name) is None for name in required):
        parser.error("Native target requires: " + ", ".join(required))
    if arguments.output.exists() or arguments.output.is_symlink():
        raise ValueError("Candidate output already exists")
    arguments.application = arguments.application.resolve(strict=True)
    media(arguments.media_package, arguments.target)
    helper(arguments.helper_package, arguments.target)
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    adapter = importlib.import_module(arguments.target.split("-", 1)[0])
    with tempfile.TemporaryDirectory(prefix="sw-native-candidate-") as temporary:
        components = adapter.prepare(arguments, Path(temporary))
        result = assemble(arguments.output, components, platform=arguments.target, source_commit=source)
    print("Native development candidate:", arguments.output, "files:", len(result["files"]))


if __name__ == "__main__":
    main()
