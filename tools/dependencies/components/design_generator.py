"""Build the source-only native Node design profile and exercise its actual API."""

import json
import os
from pathlib import Path
import subprocess


def main():
    root = Path(__file__).resolve().parents[3]
    flags = json.loads(os.environ["SYNCWATCH_DEPENDENCY_FLAGS"])
    if flags != {"profile": "native-node-v1", "version": "5.7.0"}:
        raise ValueError("Unsupported design source build configuration")
    output = Path(os.environ["SYNCWATCH_DEPENDENCY_OUTPUT"]) / "runtime"
    output.mkdir()
    subprocess.run(["node", "tools/design/build.mjs", os.environ["SYNCWATCH_DEPENDENCY_SOURCES"], str(output)], cwd=root, check=True)
    subprocess.run(["node", "--test", "tools/design/tests/runtime.test.mjs"], cwd=root, check=True,
                   env=os.environ | {"SYNCWATCH_DESIGN_RUNTIME": str(output)})


if __name__ == "__main__":
    main()
