"""Validate shared contracts using the declared pinned offline source library."""

import argparse
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/ipc"))
from syncwatch_ipc.contracts import Context, ContractError, Registry as WireRegistry, strict_json


class Registry(WireRegistry):
    def __init__(self, root: Path = ROOT):
        self.root = root.resolve()
        config = tomllib.loads((self.root / "tools/contracts/pyproject.toml").read_text())
        dependency = config["tool"]["syncwatch"]["source-dependencies"]["fastjsonschema"]
        source = self.root / dependency["path"]
        if not (source / "fastjsonschema/__init__.py").is_file():
            raise ValueError("Initialize 3rdparty/fastjsonschema before running contract checks")
        revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
        if revision != dependency["revision"]:
            raise ValueError("Contract validator source revision does not match its manifest")
        entry = subprocess.check_output(
            ["git", "ls-files", "--stage", "--", dependency["path"]], cwd=self.root, text=True,
        ).split()
        if len(entry) < 3 or entry[:3] != ["160000", revision, "0"]:
            raise ValueError("Contract validator source pin must match the Git index")
        sys.path.insert(0, str(source))
        library = importlib.import_module("fastjsonschema")
        if not Path(library.__file__).resolve().is_relative_to(source.resolve()):
            raise ValueError("Contract validator must load from the declared source submodule")
        if library.VERSION != dependency["version"]:
            raise ValueError("Contract validator source version does not match its manifest")
        super().__init__(self.root / "contracts", library)


def check_fixtures(registry: Registry) -> int:
    fixtures = strict_json((registry.directory / "fixtures/acceptance.json").read_bytes())
    seen = set()
    covered = set()
    for case in fixtures:
        name, kind = case["name"], case["schema"]
        if name in seen:
            raise ValueError("Acceptance case names must be unique")
        seen.add(name)
        covered.add(kind)
        actual = None
        try:
            value = registry.decode_frame(case["frame"].encode("utf-8")) if "frame" in case else case["value"]
            if "context" in case:
                registry.accept(kind, value, Context(**case["context"]))
            else:
                registry.validate(kind, value)
        except ContractError as error:
            actual = error.code
        if actual != case["error"]:
            raise ValueError(f"Acceptance case {name}: expected {case['error']}, received {actual}")
    if covered != set(registry.validators):
        raise ValueError("Acceptance fixtures must cover every contract entry")
    return len(fixtures)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        registry = Registry(args.root)
        count = check_fixtures(registry)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Contract checks failed: {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(registry.validators)} contracts and {count} acceptance fixtures offline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
