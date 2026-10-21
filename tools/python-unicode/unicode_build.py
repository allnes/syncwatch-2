"""Regenerate, compile and exhaustively verify original pinned Unicode type tables."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from unicode_profile import COMPONENT, ROOT, digest, encoded, original_archive, profile_data, read_sources, validate
from unicode_oracle import interchange, transcript
from native_unicode import native_proof, resolve

SUMMARY = ("SyncWatch Unicode type-table selection: unchanged original CPython generator/table/helper/public type and Unicode 15.0 inputs. "
           "The original generator runs with owned pinned readers, a fixed logical script label and LF output at creation. "
           "Range-compressed Unihan numeric sources are expanded into a separately labelled interchange for its existing ZIP reader. "
           "No original source bytes or algorithm are patched. Original full grants and notices accompany unchanged sources. "
           "The C SDK probe compiles exact original fragments and compares all code-point slots, guards and extended-case values "
           "to an independent source-derived transcript. No SDK, test executable, interpreter, embedding ABI or complete Unicode runtime is included.\n").encode()


def materialize(root, files):
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def reproduce(sources, work):
    for name, files in sources.items():
        materialize(work / name, files)
    output = work / "unicodetype_db.h"
    script = ROOT / "tools/python-unicode/generate_unicode.py"
    launcher = "import sys,runpy;sys.path.insert(0,sys.argv[1]);sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name='__main__')"
    with (work / "generation.log").open("wb") as log:
        process = subprocess.run([sys.executable, "-I", "-c", launcher, str(script.parent), str(script),
                                  str(work / "cpython"), str(work / "unicode"), str(output)],
                                 cwd=work, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                 env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1"}, timeout=60)
    if process.returncode or (work / "generation.log").stat().st_size > 1024 * 1024:
        raise ValueError("Isolated original Unicode generation failed: " + (work / "generation.log").read_bytes()[-4096:].decode("utf-8", "replace"))
    generated = output.read_bytes()
    if generated != sources["cpython"]["Objects/unicodetype_db.h"]:
        raise ValueError("Regenerated Unicode header differs from the original")
    return generated


def payload_files(sources, profile, header, proof):
    result = {"include/unicodetype_db.h": header, "sources.zip": original_archive(sources), "SELECTION.txt": SUMMARY,
              "derived/Unihan_NumericValues.txt": interchange(sources["unicode"])}
    for origin, source in profile["sources"].items():
        for notice in source["notices"]:
            result["notices/" + source["path"].split("/")[-1] + "/" + notice] = sources[origin][notice]
    result["build-report.json"] = encoded({"schemaVersion": 1, "profile": profile["profile"], "sources": profile["sources"],
        "sourceArchiveSha256": profile["sourceArchiveSha256"], "proof": proof,
        "files": {name: digest(data) for name, data in result.items()}, "originalSourcesUnchanged": True,
        "runtimeReady": False, "pinnedRuntimeBuilt": False})
    return result


def verify_files(payload, expected):
    if payload.is_symlink():
        raise ValueError("Unicode payload must not contain symbolic links")
    found = set()
    for path in payload.rglob("*"):
        if path.is_symlink():
            raise ValueError("Unicode payload must not contain symbolic links")
        if path.is_file():
            name = path.relative_to(payload).as_posix()
            if name not in expected or path.read_bytes() != expected[name]:
                raise ValueError("Unicode source, header, native proof or full notice differs: " + name)
            found.add(name)
    if found != set(expected):
        raise ValueError("Unicode payload has missing or unexpected files")


def build_or_verify(operation, sources, profile, payload, cmake, options, sdk):
    validate(sources, profile)
    oracle = transcript(sources["cpython"]["Objects/unicodetype_db.h"], sources["unicode"])
    if oracle != profile["transcript"]:
        raise ValueError("Unicode source oracle differs from the reviewed transcript")
    with tempfile.TemporaryDirectory(prefix="sw-unicode-source-") as temporary:
        header = reproduce(sources, Path(temporary))
        proof = native_proof(sources["cpython"], header, oracle, cmake, options, sdk)
    expected = payload_files(sources, profile, header, proof)
    if operation == "build":
        materialize(payload, expected)
    verify_files(payload, expected)
    return {"component": COMPONENT, "target": sdk["target"], "headerSha256": digest(header),
            "sourceFiles": sum(map(len, sources.values())), "transcript": oracle, "runtimeReady": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("identity", "build", "verify"))
    parser.add_argument("--platform", choices=("macos-arm64", "windows-x64", "linux-x64"))
    args = parser.parse_args()
    cmake, options, sdk = resolve()
    if args.operation == "identity":
        print(json.dumps(sdk, sort_keys=True)); return
    profile = profile_data()
    if args.platform and args.platform != sdk["target"]:
        raise ValueError("Unicode artifacts require native-host verification")
    if args.operation == "build":
        if json.loads(os.environ["SYNCWATCH_DEPENDENCY_FLAGS"]) != {"profile": profile["profile"], "version": profile["unicodeVersion"]}:
            raise ValueError("Unknown Unicode type-table flags")
        paths = {name: Path(os.environ["SYNCWATCH_DEPENDENCY_SOURCES"]) / source["path"] for name, source in profile["sources"].items()}
        payload = Path(os.environ["SYNCWATCH_DEPENDENCY_OUTPUT"])
    else:
        directory = ROOT / "artifacts/dependencies" / COMPONENT / sdk["target"]
        paths = {name: directory / (Path(source["path"]).name + ".tar") for name, source in profile["sources"].items()}
        payload = directory / "payload"
    result = build_or_verify(args.operation, read_sources(paths, profile), profile, payload, cmake, options, sdk)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
