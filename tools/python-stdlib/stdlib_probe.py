"""Run real package/startup C APIs with only the verified owned encoding ZIP on sys.path."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

from stdlib_profile import COMPONENT, ROOT, profile_data

sys.path.insert(0, str(ROOT / "tools/python-runtime"))
from native_sdk import resolve as python_sdk, sha
from native_probe import execute
sys.path.insert(0, str(ROOT / "tools/hashing"))
from hash_sdk import resolve as native_sdk

CASES = ("success", "corrupt", "missing", "extra")


def prerequisite(component, target):
    execute([sys.executable, "tools/dependencies/build.py", "build", "--component", component, "--platform", target], ROOT)
    directory = ROOT / "artifacts/dependencies" / component / target
    with zipfile.ZipFile(directory / "artifact.zip") as archive:
        data = archive.read("build-manifest.json")
    manifest = json.loads(data)
    if manifest["result"] != "success" or manifest["inputs"]["platform"] != target:
        raise ValueError("Native bootstrap prerequisite was not freshly verified")
    return directory / "payload", {"key": manifest["key"], "manifestSha256": hashlib.sha256(data).hexdigest()}


def fixture(root, archive, profile):
    roots = [root / name for name in CASES]
    for directory in roots:
        directory.mkdir()
        (directory / "stdlib.zip").write_bytes(archive)
    corrupted = bytearray(archive)
    corrupted[len(corrupted) // 2] ^= 1
    (roots[1] / "stdlib.zip").write_bytes(corrupted)
    (roots[2] / "stdlib.zip").unlink()
    (roots[3] / "unexpected.py").write_text("raise RuntimeError('unreviewed source')\n", encoding="utf-8")
    executable = roots[0] / "owned-helper"
    inputs = {"EXPECTED_ARCHIVE": str(roots[0] / "stdlib.zip"), "EXPECTED_ROOT": str(roots[0]),
              "EXPECTED_EXECUTABLE": str(executable), "CODECS": profile["codecs"],
              "VECTORS": profile["vectors"],
              "UNSUPPORTED_CODECS": profile["unsupportedExamples"]}
    # Python escapes retain Unicode values while C character initializers remain portable ASCII.
    script = "\n".join(name + " = " + ascii(value) for name, value in inputs.items()) + "\n"
    script += (ROOT / "tools/python-stdlib/native/checks.py").read_text(encoding="utf-8")
    wide = lambda value: "L" + json.dumps(str(value), ensure_ascii=True)
    header = ("static const char *fixture_names[] = {" + ",".join(json.dumps(n) for n in CASES) + "};\n"
              "static const wchar_t *fixture_roots[] = {" + ",".join(wide(p) for p in roots) + "};\n"
              "static const wchar_t *fixture_executable = " + wide(executable) + ";\n"
              "static const sw_package_file fixture_file = {L\"stdlib.zip\", " + str(len(archive)) + ", {" +
              ",".join(str(n) for n in hashlib.sha256(archive).digest()) + "}};\n"
              "static const sw_package_result fixture_errors[] = {SW_PACKAGE_OK, SW_PACKAGE_DIGEST_MISMATCH, "
              "SW_PACKAGE_MISSING_ENTRY, SW_PACKAGE_UNEXPECTED_ENTRY};\n"
              "static const char fixture_checks[] = {" + ",".join(str(n) for n in script.encode("ascii")) + ",0};\n")
    (root / "fixture.h").write_text(header, encoding="utf-8", newline="\n")
    poison = root / "poison"
    poison.mkdir()
    for name in ("syncwatch_poison", "json", "sitecustomize", "usercustomize"):
        (poison / (name + ".py")).write_text("raise RuntimeError('Controlled poison executed')\n", encoding="utf-8")
    (poison / "encodings").mkdir()
    (poison / "encodings/__init__.py").write_text("raise RuntimeError('Poisoned encodings executed')\n", encoding="utf-8")
    environment = {key: value for key, value in os.environ.items() if key.upper() in {"SYSTEMROOT", "WINDIR"}}
    environment.update(TEMP=str(root), TMP=str(root), PYTHONHOME=str(poison), PYTHONPATH=str(poison),
                       PYTHONUSERBASE=str(poison), PYTHONUTF8="0", PYTHONINSPECT="1", PYTHONSTARTUP=str(poison / "json.py"))
    return poison, environment


def probe():
    profile = profile_data()
    sdk, identity = python_sdk()
    cmake, options, compiler, _symbols = native_sdk()
    stdlib, stdlib_identity = prerequisite(COMPONENT, compiler["target"])
    hashing, hash_identity = prerequisite("hacl-hash", compiler["target"])
    archive = (stdlib / "stdlib.zip").read_bytes()
    analysis = json.loads((stdlib / "source-analysis.json").read_bytes())
    if hashlib.sha256(archive).hexdigest() != profile["stdlibSha256"]:
        raise ValueError("Accepted bootstrap stdlib bytes changed")
    with tempfile.TemporaryDirectory(prefix="sw-bootstrap-stdlib-") as temporary:
        root = Path(temporary).resolve() / "package-\u03bc-\u0442\u0435\u0441\u0442"
        root.mkdir()
        poison, environment = fixture(root, archive, profile)
        if sys.platform == "win32":
            environment["PATH"] = str(sdk["runtime"].parent)
        build = root / "build"
        execute([cmake, "-S", (ROOT / "tools/python-stdlib/native").as_posix(), "-B", build.as_posix(), *options,
                 "-DCMAKE_BUILD_TYPE=Release", "-DSYNCWATCH_ROOT=" + ROOT.as_posix(), "-DSYNCWATCH_FIXTURE=" + root.as_posix(),
                 "-DSYNCWATCH_HASH=" + hashing.as_posix(), "-DSYNCWATCH_PYTHON_INCLUDE=" + sdk["include"].as_posix(),
                 "-DSYNCWATCH_PYTHON_LIBRARY=" + sdk["library"].as_posix()], ROOT)
        execute([cmake, "--build", build.as_posix(), "--config", "Release", "--parallel", "2"], ROOT)
        binary = Path((build / "probe-Release.txt").read_text(encoding="utf-8"))
        cases = {}
        outputs = {}
        for name in CASES:
            try:
                data = execute([str(binary), name], poison, environment, timeout=30)
            except ValueError as error:
                raise ValueError("Native bootstrap case failed: " + name) from error
            if data.count(b"SYNCWATCH_BOOTSTRAP_STDLIB_OK") != 1:
                raise ValueError("Native bootstrap case did not report success: " + name)
            if name == "success":
                counts = re.findall(rb"^SYNCWATCH_BOOTSTRAP_CODECS (\d+) (\d+)\r?$", data, re.MULTILINE)
                if counts != [(str(len(profile["codecs"])).encode(), str(len(analysis["selectedAliases"])).encode())]:
                    raise ValueError("Native codec/alias execution count differs from the reviewed source")
            cases[name] = True
            outputs[name] = {"sha256": hashlib.sha256(data).hexdigest(), "text": data.decode("ascii")}
        if list(root.rglob("*.pyc")) or list(root.rglob("__pycache__")):
            raise ValueError("Native bootstrap wrote unexpected bytecode")
        binary_sha = sha(binary)
    files = [p for directory in [ROOT / "tools/python-stdlib", ROOT / "packages/python-package", ROOT / "packages/python-startup"]
             for p in directory.rglob("*") if p.is_file() and p.suffix in {".py", ".c", ".h", ".json", ".txt", ".toml"}]
    files += [ROOT / "tools/python-runtime/native_sdk.py", ROOT / "tools/python-runtime/native_probe.py",
              ROOT / "tools/python-runtime/profile.json", ROOT / "tools/compression/toolchain.py", ROOT / "tools/hashing/hash_sdk.py"]
    return {"developerSdkOnly": True, "sdk": identity, "compiler": compiler, "cases": cases, "caseOutputs": outputs,
            "stdlibSha256": profile["stdlibSha256"], "encodingModules": len(profile["codecs"]) + 2,
            "codecsExecuted": len(profile["codecs"]), "aliasesExecuted": len(analysis["selectedAliases"]),
            "stdlibArtifact": stdlib_identity, "hashArtifact": hash_identity, "probeSha256": binary_sha,
            "firstPartyFiles": {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(files)},
            "sdkStandardLibrarySearchPaths": 0, "ownedZipOnly": True, "testRuntimeDistributed": False,
            "pinnedRuntimeBuilt": False, "pinnedEmbeddingAbiVerified": False, "runtimeReady": False,
            "packageAuthenticityVerified": False, "installationImmutabilityVerified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = probe()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
