"""Build and verify a reviewed, non-executable Syncplay source artifact."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import subprocess
import sys
import tarfile
import tempfile
import zipfile

from source_analysis import analyze


ROOT = Path(__file__).resolve().parents[2]
COMPONENT = "syncplay-engine-sources"
ARCHIVE = "syncplay-engine-sources.zip"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def safe_name(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or str(path) != name or any(p in {".", ".."} for p in path.parts)
            or any(c in name for c in ("\\", ":", "\x00"))):
        raise ValueError("Unsafe source snapshot member")


def profile_data():
    profile = json.loads((ROOT / "tools/syncplay/profile.json").read_text())
    registry = json.loads((ROOT / "tools/dependencies/components.json").read_text())["components"]
    if profile["schemaVersion"] != 1 or profile["runtimeReady"] is not False:
        raise ValueError("Only the reviewed non-executable source profile is supported")
    expected = {k: profile["source"][k] for k in ("revision", "license", "notices", "exports")}
    expected.update(requires=[], unusedSubmodules={})
    component = registry[COMPONENT]
    if component["sources"] != {profile["source"]["path"]: expected} or component["roots"] != [profile["source"]["path"]]:
        raise ValueError("Engine source/license profile differs from the registered graph")
    if registry["syncplay-runtime"]["status"] != "unavailable":
        raise ValueError("Source packaging cannot enable an unresolved runtime")
    return profile


def read_snapshot(path, specification):
    files = {}
    if path.is_dir():
        for entry in path.rglob("*"):
            if entry.is_symlink():
                raise ValueError("Source snapshot requires regular files")
            if entry.is_file():
                name = entry.relative_to(path).as_posix()
                safe_name(name)
                files[name] = entry.read_bytes()
    else:
        with tarfile.open(path) as archive:
            if archive.pax_headers.get("comment") != specification["revision"]:
                raise ValueError("Source snapshot has a different Git revision")
            for entry in archive:
                safe_name(entry.name)
                if entry.isdir():
                    continue
                if not entry.isfile() or entry.name in files:
                    raise ValueError("Source snapshot requires unique regular files")
                files[entry.name] = archive.extractfile(entry).read()
    if set(files) != set(specification["files"]):
        raise ValueError("Source snapshot differs from the exact file inventory")
    for name, data in files.items():
        if digest(data) != specification["files"][name]:
            raise ValueError("Source or notice digest changed: " + name)
    return files


def archive_bytes(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            safe_name(name)
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return stream.getvalue()


def payload_files(files, profile):
    analysis = analyze(files, profile["standardLibraryRoots"])
    if digest(encoded(analysis)) != profile["analysisSha256"]:
        raise ValueError("Import/API/configuration analysis differs from the reviewed profile")
    archive = archive_bytes(files)
    if digest(archive) != profile["archiveSha256"]:
        raise ValueError("Unchanged source archive differs from the reviewed profile")
    result = {ARCHIVE: archive, "source-analysis.json": encoded(analysis),
              "source-manifest.json": encoded({"schemaVersion": 1, "runtimeReady": False,
                                               "version": profile["version"], "source": profile["source"],
                                               "sourceArchiveSha256": digest(archive),
                                               "analysisSha256": digest(encoded(analysis))})}
    for name in profile["source"]["notices"]:
        result["notices/syncplay/" + name] = files[name]
    return result


def verify(payload, expected):
    found = set()
    for entry in payload.rglob("*"):
        if entry.is_symlink():
            raise ValueError("Source payload must not contain symbolic links")
        if entry.is_file():
            name = entry.relative_to(payload).as_posix()
            found.add(name)
            if name not in expected or entry.read_bytes() != expected[name]:
                raise ValueError("Source payload or notice differs: " + name)
    if found != set(expected):
        raise ValueError("Source payload has missing or unexpected files")


def smoke(archive, version):
    with tempfile.TemporaryDirectory(prefix="syncwatch-engine-source-") as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            for name in package.namelist():
                safe_name(name)
            package.extractall(root)
        process = subprocess.run([sys.executable, "-I", "-S", "-B", str(ROOT / "tools/syncplay/smoke.py"), str(root), version],
                                 text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        if process.returncode:
            raise ValueError("Isolated upstream module probe failed:\n" + process.stdout)
        result = json.loads(process.stdout)
        if result["runtimeReady"] is not False or result["engineInitialized"] is not False or result["attempts"] != []:
            raise ValueError("Unexpected isolated upstream module probe")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "verify"))
    parser.add_argument("--platform", choices=("linux-x64", "macos-arm64", "windows-x64"))
    args = parser.parse_args()
    profile = profile_data()
    if args.operation == "build":
        if json.loads(os.environ["SYNCWATCH_DEPENDENCY_FLAGS"]) != {"profile": "reviewed-engine-sources-v1", "version": profile["version"]}:
            raise ValueError("Unknown engine source build profile")
        snapshot = Path(os.environ["SYNCWATCH_DEPENDENCY_SOURCES"]) / profile["source"]["path"]
        payload = Path(os.environ["SYNCWATCH_DEPENDENCY_OUTPUT"])
    else:
        target = args.platform or {("Darwin", "arm64"): "macos-arm64", ("Linux", "x86_64"): "linux-x64", ("Windows", "AMD64"): "windows-x64"}[(platform.system(), platform.machine())]
        directory = ROOT / "artifacts/dependencies" / COMPONENT / target
        snapshot, payload = directory / "syncplay.tar", directory / "payload"
    files = read_snapshot(snapshot, profile["source"])
    expected = payload_files(files, profile)
    if args.operation == "build":
        for name, data in expected.items():
            target = payload / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    verify(payload, expected)
    probe = smoke(expected[ARCHIVE], profile["version"])
    languages = sorted(n.removeprefix("syncplay/messages_").removesuffix(".py") for n in files
                       if n.startswith("syncplay/messages_") and n.endswith(".py"))
    if probe["languages"] != languages:
        raise ValueError("Upstream languages differ from the selected source inventory")
    print(json.dumps({"verified": COMPONENT, "runtimeReady": False, "sourceFiles": len(files),
                      "archiveSha256": profile["archiveSha256"], "analysisSha256": profile["analysisSha256"], "probe": probe}, sort_keys=True))


if __name__ == "__main__":
    main()
