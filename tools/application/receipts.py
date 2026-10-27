"""Read existing native input receipts before staging an application candidate."""

import json
from pathlib import Path
import platform
import re
import subprocess

from candidate_tree import inventory


ROOT = Path(__file__).resolve().parents[2]


def source_inputs(root=ROOT):
    """Retain exact first-party overlays as well as their Git base commit."""
    import sys
    sys.path.insert(0, str(ROOT / "tools/dependencies"))
    import build as dependencies
    specification = {"verificationInputs": ["apps", "packages", "contracts", "tools", "global.json", "LICENSE", ".gitmodules"]}
    return {"commit": dependencies.git(root, "rev-parse", "HEAD").decode().strip(),
            "localChanges": bool(dependencies.git(root, "status", "--porcelain", "--untracked-files=normal").strip()),
            "files": dependencies.input_files(root, specification, verification=True)}


def require_host(target):
    actual = {("Darwin", "arm64"): "macos-arm64", ("Windows", "AMD64"): "windows-x64",
              ("Linux", "x86_64"): "linux-x64"}.get((platform.system(), platform.machine()))
    if actual != target:
        raise ValueError("Application packaging requires its native OS and architecture")


def pin(path):
    fields = subprocess.check_output(["git", "ls-files", "--stage", "--", path], cwd=ROOT, text=True).split()
    if len(fields) != 4 or fields[0] != "160000" or fields[2] != "0":
        raise ValueError("Application runtime requires a registered source Gitlink")
    return fields[1]


def checked_receipt(package, filename, *, schema_version=1):
    package = Path(package).resolve(strict=True)
    contents = inventory(package)
    if contents.get(filename, {}).get("kind") != "file":
        raise ValueError("Missing regular runtime receipt")
    receipt = json.loads((package / filename).read_text(encoding="utf-8"))
    files = receipt.get("files")
    actual = {name: data["sha256"] for name, data in contents.items() if data["kind"] == "file" and name != filename}
    if (receipt.get("schemaVersion") != schema_version or not isinstance(files, dict) or not files or files != actual
            or any(data["kind"] == "link" for data in contents.values())
            or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in files.values())):
        raise ValueError("Runtime receipt differs from actual package bytes")
    return receipt


def renderer(package):
    require_host("linux-x64")
    # The existing native SDK receipt predates schemaVersion; keep its exact inventory contract.
    receipt = checked_receipt(package, "native-objects.json", schema_version=None)
    profile = json.loads((ROOT / "tools/desktop/profile.json").read_text())
    if receipt.get("profile") != profile["profile"] or receipt.get("nativeRendererLinked") is not True:
        raise ValueError("Linux renderer differs from the declared source-built native SDK")
    return receipt


def clients(package):
    require_host("linux-x64")
    receipt = checked_receipt(package, "clients-report.json")
    profile = json.loads((ROOT / "tools/application/linux-clients.json").read_text())
    if (receipt.get("target") != "linux-x64" or receipt.get("sourceBuilt") is not True
            or receipt.get("sources") != profile["sources"]
            or any(data["revision"] != pin(data["path"]) for data in profile["sources"].values())
            or any("lib/" + name not in receipt["files"] for name in profile["runtimeLibraries"])
            or any(receipt["files"].get("sources/" + name + ".tar") != data["archiveSha256"]
                   for name, data in profile["sources"].items())):
        raise ValueError("Dynamic X11 clients differ from their registered source graph")
    return receipt


def media(package, target):
    receipt = checked_receipt(package, "build-report.json")
    if receipt.get("sdk", {}).get("target") != target or receipt.get("sources", {}).get("vlc", {}).get("revision") != pin("3rdparty/vlc"):
        raise ValueError("Media runtime target or source pin differs")
    return receipt


def helper(package, target):
    receipt = checked_receipt(package, "helper-report.json")
    executable = "bin/syncwatch-helper" + (".exe" if target == "windows-x64" else "")
    if (receipt.get("target") != target or receipt.get("syncplayRevision") != pin("3rdparty/syncplay")
            or receipt.get("developmentHelperOnly") is not True or receipt.get("authenticatedInstallation") is not False
            or executable not in receipt["files"] or "app/syncplay-revision.txt" not in receipt["files"]
            or (Path(package) / "app/syncplay-revision.txt").read_text().strip() != receipt["syncplayRevision"]):
        raise ValueError("Helper target, source pin or development package differs")
    return receipt


def jvm(package):
    receipt = checked_receipt(package, "jvm-report.json")
    profile = json.loads((ROOT / "tools/application/jvm-profile.json").read_text())
    if (receipt.get("target") != "linux-x64" or receipt.get("sourceRevision") != pin("3rdparty/openjdk")
            or receipt.get("sourceBuilt") is not True or receipt.get("developerSdk") is not False
            or receipt.get("sources") != profile["sources"] or receipt.get("modules") != profile["moduleRoots"]
            or not {"bin/java", "lib/modules", "lib/server/libjvm.so"}.issubset(receipt["files"])
            or any(receipt["files"].get("sources/" + name + ".tar.gz") != data["archiveSha256"]
                   for name, data in profile["sources"].items())):
        raise ValueError("Linux application requires its reviewed source-built JVM")
    return receipt


def desktop_classpath(package):
    """Match every distributed JVM library to the existing reviewed Linux compiler output."""
    require_host("linux-x64")
    import hashlib
    import sys
    sys.path.insert(0, str(ROOT / "tools/jvm"))
    import annotations
    import compose_ui
    import compose_state
    import compose_runtime
    import concurrency
    import jbr_api
    import stdlib
    package = Path(package).resolve(strict=True)
    expected = {}
    for module, directory in ((compose_ui, package), (compose_state, package / "parent"),
                              (compose_runtime, package / "parent/parent")):
        for name, digest in module.profile_data()["expectedJars"]["linux-x64"].items():
            expected[directory / name] = digest
    concurrency_pins = concurrency.profile_data()["expectedJars"]["linux-x64"]
    for name in concurrency.BINARIES.values():
        expected[package / "parent/parent/parent" / name] = concurrency_pins[name]
    runtime = package / "parent/parent/parent/runtime"
    expected[runtime / stdlib.BINARY] = stdlib.profile_data()[0]["expectedJars"]["linux-x64"][stdlib.BINARY]
    expected[runtime / "annotations" / annotations.BINARY] = annotations.profile_data()[0]["expectedJars"][annotations.BINARY]
    expected[package / "jbr-api" / jbr_api.BINARY] = jbr_api.profile_data()[0]["expectedJars"][jbr_api.BINARY]
    classpath = compose_ui.paths(package, compose_ui.profile_data())
    if set(classpath) != set(expected):
        raise ValueError("Desktop JVM classpath differs from the reviewed complete library set")
    for path, digest in expected.items():
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(package):
            raise ValueError("Desktop JVM library leaves its owned package")
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                raise ValueError("Desktop JVM library differs from its reviewed compiler output: " + path.name)
    return classpath
