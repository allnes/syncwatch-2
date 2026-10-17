"""Generate native resources or check committed output using the verified source-built tool."""

import argparse
from pathlib import Path
import platform
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Reject changes instead of writing generated files")
    parser.add_argument("--cold", action="store_true", help="Build the tool without reading its dependency cache")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    subprocess.run([sys.executable, "tools/design/check.py", *(["--cold"] if args.cold else [])], cwd=root, check=True)
    targets = {("Darwin", "arm64"): "macos-arm64", ("Linux", "x86_64"): "linux-x64", ("Windows", "AMD64"): "windows-x64"}
    target = targets[(platform.system(), platform.machine())]
    runtime = root / "artifacts/dependencies/design-generator" / target / "payload/runtime"
    subprocess.run(["node", "tools/design/generate.mjs", "--runtime", str(runtime), *(["--check"] if args.check else [])], cwd=root, check=True)


if __name__ == "__main__":
    main()
