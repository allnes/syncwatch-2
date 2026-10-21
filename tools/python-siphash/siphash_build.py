"""Package exact originals and freshly verify CPython's raw SipHash source fragments."""

import argparse
import json
import os
from pathlib import Path

from siphash_profile import COMPONENT, ROOT, analyze, digest, encoded, original_archive, profile_data, read_sources, validate
from siphash_oracle import corpus_header, transcript
from native_siphash import native_proof, resolve

SUMMARY = ("SyncWatch CPython raw SipHash provenance selection: seven unchanged CPython files and three unchanged csiphash origin/reference files. "
           "Complete original MIT/PSF historical grants, credits and original modification attribution accompany the sources. "
           "CPython's existing modified source is retained; it is not byte-identical to the earlier origin. "
           "Only exact original size typedef/configuration and SipHash13/SipHash24/_Py_KeyedHash fragments enter the C SDK fixture. "
           "The csiphash implementation and its POSIX test program remain reference inputs and are not compiled. "
           "First-party public fixture configuration selects supported 64-bit little-endian hosts and both original round variants. "
           "The independent model/corpus and generic native transcript harness are separate first-party additions. "
           "No original source/algorithm is patched. No Python C SDK, test executable, library, interpreter or embedding ABI is distributed. "
           "This does not establish full Python hash API, runtime entropy, cryptographic approval or Syncplay readiness.\n").encode()


def materialize(root, files):
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def payload_files(sources, profile, proof):
    result = {"sources.zip": original_archive(sources), "source-analysis.json": encoded(analyze(sources)), "SELECTION.txt": SUMMARY}
    for origin, source in profile["sources"].items():
        for name in source["notices"]:
            result["notices/" + source["path"].split("/")[-1] + "/" + name] = sources[origin][name]
    result["build-report.json"] = encoded({"schemaVersion": 1, "profile": profile["profile"], "sources": profile["sources"],
        "sourceArchiveSha256": profile["sourceArchiveSha256"], "analysisSha256": profile["analysisSha256"], "proof": proof,
        "files": {name: digest(data) for name, data in result.items()}, "originalSourcesUnchanged": True,
        "originReferenceCompiled": False, "runtimeReady": False, "pinnedRuntimeBuilt": False})
    return result


def verify_files(payload, expected):
    if payload.is_symlink():
        raise ValueError("SipHash payload must not contain symbolic links")
    found = set()
    for path in payload.rglob("*"):
        if path.is_symlink():
            raise ValueError("SipHash payload must not contain symbolic links")
        if path.is_file():
            name = path.relative_to(payload).as_posix()
            if name not in expected or path.read_bytes() != expected[name]:
                raise ValueError("SipHash source, native proof or full notice differs: " + name)
            found.add(name)
    if found != set(expected):
        raise ValueError("SipHash payload has missing or unexpected files")


def build_or_verify(operation, sources, profile, payload, cmake, options, sdk):
    validate(sources, profile)
    expected = transcript(sources)
    if expected != profile["transcript"] or digest(corpus_header(sources)) != profile["corpusSha256"]:
        raise ValueError("SipHash independent corpus or oracle differs from the reviewed profile")
    proof = native_proof(sources, expected, cmake, options, sdk)
    files = payload_files(sources, profile, proof)
    if operation == "build":
        materialize(payload, files)
    verify_files(payload, files)
    return {"component": COMPONENT, "target": sdk["target"], "sourceFiles": sum(map(len, sources.values())),
            "transcript": expected, "runtimeReady": False}


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
        raise ValueError("SipHash artifacts require native-host verification")
    if args.operation == "build":
        if json.loads(os.environ["SYNCWATCH_DEPENDENCY_FLAGS"]) != {"profile": profile["profile"]}:
            raise ValueError("Unknown SipHash source profile")
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
