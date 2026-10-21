"""Compile exact static sources and compare fresh/cache archive bytes before execution."""

import json
import os
from pathlib import Path
import re
import subprocess

from source_profile import ROOT, digest, encoded


def execute(args, timeout=180):
    subprocess.run(args, cwd=ROOT, env=os.environ | {"ZERO_AR_DATE": "1"}, check=True, timeout=timeout)


def materialize(root, files):
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def compile_native(cmake, sdk_args, root, directory, library=None):
    command = [cmake, "-S", (ROOT / "tools/hashing").as_posix(), "-B", directory.as_posix(), *sdk_args,
               "-DCMAKE_BUILD_TYPE=Release"]
    for name, path in [("SOURCE", root / "sources"), ("HEADERS", root / "headers/include"),
                       ("FIXTURES", root), ("WORK", root)]:
        command.append("-DSYNCWATCH_" + name + "=" + path.as_posix())
    if library:
        command.append("-DSYNCWATCH_ARTIFACT=" + library.as_posix())
    execute(command)
    execute([cmake, "--build", directory.as_posix(), "--config", "Release", "--parallel", "2"])
    return tuple(Path((directory / (kind + "-Release.txt")).read_text(encoding="utf-8")) for kind in ["library", "probe"])


def require_identical(expected, actual):
    if expected != actual:
        offset = next((i for i, pair in enumerate(zip(expected, actual)) if pair[0] != pair[1]), min(len(expected), len(actual)))
        raise ValueError("Fresh hash compilation changed static archive bytes: " + json.dumps({
            "expectedSha256": digest(expected), "actualSha256": digest(actual), "firstDifference": offset,
            "expectedContext": repr(expected[max(0, offset-16):offset+64]), "actualContext": repr(actual[max(0, offset-16):offset+64])}))


def inspect_symbols(tool, library, target, profile):
    args = [tool, "/nologo", "/linkermember:1", str(library)] if target == "windows-x64" else [
        tool, "-g", "-U" if target == "macos-arm64" else "--defined-only", str(library)]
    result = subprocess.run(args, capture_output=True, timeout=30)
    if result.returncode or len(result.stdout) > 1024 * 1024:
        raise ValueError("Native SDK symbol inspection failed or exceeded bounds")
    symbols = set()
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        parts = line.split()
        token = parts[-1].lstrip("_") if parts else ""
        if re.fullmatch(r"(?:python_hashlib_)?Hacl_\w+", token):
            symbols.add(token)
    if (not symbols or any(not name.startswith(profile["namespacePrefix"]) for name in symbols)
            or not {profile["namespacePrefix"] + name for name in profile["requiredSymbols"]} <= symbols):
        raise ValueError("Hash archive has missing or unprefixed native symbols")
    return sorted(symbols)


def probe(executable, expected):
    process = subprocess.run([str(executable)], stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
    if process.returncode or len(process.stdout) > 4096 or len(process.stderr) > 4096:
        raise ValueError("Native hash API probe failed: " + process.stderr[:4096].decode("utf-8", errors="replace"))
    try:
        actual = json.loads(process.stdout)
    except ValueError as error:
        raise ValueError("Native hash API returned invalid JSON") from error
    if encoded(actual) != encoded(expected):
        raise ValueError("Native hash API did not satisfy its exact fixture contract")
    return actual
