"""Build and check the native design-tool source profile without registry packages."""

import argparse
from pathlib import Path
import platform
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cold", action="store_true", help="Ignore previously verified dependency cache bytes")
    args = parser.parse_args()
    targets = {("Darwin", "arm64"): "macos-arm64", ("Linux", "x86_64"): "linux-x64", ("Windows", "AMD64"): "windows-x64"}
    target = targets.get((platform.system(), platform.machine()))
    if target is None:
        raise ValueError("Unsupported design build platform")
    root = Path(__file__).resolve().parents[2]
    base = [sys.executable, "tools/dependencies/build.py"]
    options = ["--component", "design-generator", "--platform", target]
    subprocess.run([*base, "prepare", *options], cwd=root, check=True)
    subprocess.run([*base, "build", *options, *(["--cold"] if args.cold else [])], cwd=root, check=True)
    # Check notice presence and modification markers on both cold builds and cache restores.
    runtime = root / "artifacts/dependencies/design-generator" / target / "payload/runtime"
    subprocess.run(["node", "tools/design/licenses.mjs", str(runtime)], cwd=root, check=True)


if __name__ == "__main__":
    main()
