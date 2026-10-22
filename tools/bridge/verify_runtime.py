"""Revalidate the owned base runtime using the current native-owner engine fixture."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/syncplay-runtime"))
sys.path.insert(0, str(ROOT / "tools/python-runtime"))
sys.path.insert(0, str(ROOT / "tools/python-build"))
sys.path.insert(0, str(ROOT / "tools/dependencies"))
from engine_package import relocated_probe


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    receipt = json.loads((args.runtime / "build-report.json").read_text(encoding="utf-8"))
    result = relocated_probe(args.runtime.resolve(), receipt["sdk"]["native"]["target"])
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
