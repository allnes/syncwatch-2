"""Build and freshly recompile a source-pinned static hash artifact on its native host."""

import argparse
import json
import os
from pathlib import Path
import tempfile

import fixtures
from native_build import compile_native, inspect_symbols, materialize, probe, require_identical
from hash_sdk import resolve
from source_profile import COMPONENT, ROOT, SUMMARY, digest, encoded, original_archive, profile_data, public_headers, read_sources, validate_sources


def payload_files(sources, profile, sdk, library, symbols, report):
    if not library.startswith(b"!<arch>\n"):
        raise ValueError("Expected a static native hash archive")
    name = "syncwatch_hacl.lib" if sdk["target"] == "windows-x64" else "libsyncwatch_hacl.a"
    result = public_headers(sources, profile) | {"lib/" + name: library, "sources.zip": original_archive(sources), "SELECTION.txt": SUMMARY}
    for origin, source in profile["sources"].items():
        for notice in source["notices"]:
            result["notices/" + origin + "/" + notice] = sources[origin][notice]
    result["build-report.json"] = encoded({"schemaVersion": 1, "profile": profile["profile"], "sources": profile["sources"],
        "sdk": sdk, "symbols": symbols, "probe": report, "sourceArchiveSha256": profile["sourceArchiveSha256"],
        "originalSourcesUnchanged": True, "verifiedUint128": True, "sharedLibrary": False, "runtimeReady": False,
        "archiveEnvironment": {"ZERO_AR_DATE": "1"},
        "files": {name: digest(data) for name, data in result.items()}})
    return result


def verify_files(payload, expected):
    found = set()
    for path in payload.rglob("*"):
        if path.is_symlink():
            raise ValueError("Hash payload must not contain symbolic links")
        if path.is_file():
            name = path.relative_to(payload).as_posix()
            if name not in expected or path.read_bytes() != expected[name]:
                raise ValueError("Hash source, notice, header or payload differs: " + name)
            found.add(name)
    if found != set(expected):
        raise ValueError("Hash payload has missing or unexpected files")


def build_or_verify(operation, payload, sources, profile, cmake, options, sdk, symbol_tool):
    validate_sources(sources, profile)
    fixture, count = fixtures.header(ROOT / "tools/hashing/vectors.json", profile["algorithms"])
    expected_probe = fixtures.expected_report(count)
    with tempfile.TemporaryDirectory(prefix="sw-hash-") as temporary:
        root = Path(temporary).resolve()
        for name, files in sources.items():
            materialize(root / "sources" / name, files)
        materialize(root / "headers", public_headers(sources, profile))
        (root / "vectors.h").write_bytes(fixture)
        library, executable = compile_native(cmake, options, root, root / "fresh")
        fresh = library.read_bytes()
        symbols = inspect_symbols(symbol_tool, library, sdk["target"], profile)
        result = probe(executable, expected_probe)
        if operation == "build":
            repeated, repeated_probe = compile_native(cmake, options, root, root / "repeat")
            require_identical(fresh, repeated.read_bytes())
            probe(repeated_probe, expected_probe)
            expected = payload_files(sources, profile, sdk, fresh, symbols, result)
            materialize(payload, expected)
        else:
            archive = payload / "lib" / ("syncwatch_hacl.lib" if sdk["target"] == "windows-x64" else "libsyncwatch_hacl.a")
            expected = payload_files(sources, profile, sdk, fresh, symbols, result)
            verify_files(payload, expected)
            require_identical(fresh, archive.read_bytes())
            _unused, accepted_probe = compile_native(cmake, options, root, root / "accepted", archive)
            probe(accepted_probe, expected_probe)
            if inspect_symbols(symbol_tool, archive, sdk["target"], profile) != symbols:
                raise ValueError("Accepted hash archive symbol inventory differs")
        verify_files(payload, expected)
    return {"component": COMPONENT, "target": sdk["target"], "sourceFiles": sum(map(len, sources.values())),
            "sourceArchiveSha256": profile["sourceArchiveSha256"], "symbols": len(symbols), "probe": result, "runtimeReady": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["identity", "build", "verify"])
    parser.add_argument("--platform", choices=["macos-arm64", "windows-x64", "linux-x64"])
    args = parser.parse_args()
    cmake, options, sdk, symbol_tool = resolve()
    if args.operation == "identity":
        print(json.dumps(sdk, sort_keys=True));return
    profile = profile_data()
    if args.platform and args.platform != sdk["target"]:
        raise ValueError("Hash artifacts require native-host verification")
    if args.operation == "build":
        if json.loads(os.environ["SYNCWATCH_DEPENDENCY_FLAGS"]) != {"profile": "static-hash-v1", "verifiedUint128": True}:
            raise ValueError("Unknown native hash build flags")
        paths = {name: Path(os.environ["SYNCWATCH_DEPENDENCY_SOURCES"]) / source["path"] for name, source in profile["sources"].items()}
        payload = Path(os.environ["SYNCWATCH_DEPENDENCY_OUTPUT"])
    else:
        directory = ROOT / "artifacts/dependencies" / COMPONENT / sdk["target"]
        paths = {name: directory / (name + ".tar") for name in profile["sources"]}
        payload = directory / "payload"
    sources = read_sources(paths, profile)
    print(json.dumps(build_or_verify(args.operation, payload, sources, profile, cmake, options, sdk, symbol_tool), sort_keys=True))


if __name__ == "__main__":
    main()
