"""Build and exercise the metadata server with the exact SDK and pinned contract validator."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[2]


def provision(specification, target, directory):
    source = specification["sources"][target]
    url = urllib.parse.urlsplit(source["url"])
    version = specification["sdkVersion"]
    if url.scheme != "https" or url.hostname != "builds.dotnet.microsoft.com" or url.username or url.password:
        raise ValueError("SDK source must be the declared official HTTPS origin")
    if not re.fullmatch(r"[0-9a-f]{128}", source["sha512"]):
        raise ValueError("SDK archive requires a SHA-512 digest")
    directory.mkdir(parents=True, exist_ok=True)
    sdk = directory / ("dotnet-" + version + "-" + target)
    executable = sdk / ("dotnet.exe" if target == "win-x64" else "dotnet")
    if executable.is_file():
        return executable
    archive = directory / ("sdk.zip" if target == "win-x64" else "sdk.tar.gz")
    partial = directory / ("extract-" + target)
    if partial.exists():
        shutil.rmtree(partial)
    try:
        urllib.request.urlretrieve(source["url"], archive)
        with archive.open("rb") as data:
            if hashlib.file_digest(data, "sha512").hexdigest() != source["sha512"]:
                raise ValueError("SDK archive digest mismatch")
        partial.mkdir()
        if target == "win-x64":
            with zipfile.ZipFile(archive) as data:
                for member in data.infolist():
                    destination = (partial / member.filename).resolve()
                    if not destination.is_relative_to(partial.resolve()):
                        raise ValueError("SDK archive path leaves extraction directory")
                data.extractall(partial)
        else:
            with tarfile.open(archive) as data:
                data.extractall(partial, filter="data")
        partial.rename(sdk)
        return executable
    finally:
        archive.unlink(missing_ok=True)
        if partial.exists():
            shutil.rmtree(partial)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dotnet")
    parser.add_argument("--provision", action="store_true")
    args = parser.parse_args()
    spec = json.loads((ROOT / "tools/server/toolchains.json").read_text())
    if spec["sdkVersion"] != json.loads((ROOT / "global.json").read_text())["sdk"]["version"]:
        raise ValueError("Server SDK must match global.json")
    targets = {("Darwin", "arm64"): "osx-arm64", ("Linux", "x86_64"): "linux-x64", ("Windows", "AMD64"): "win-x64"}
    target = targets.get((platform.system(), platform.machine()))
    if target is None:
        raise ValueError("Unsupported server validation platform")
    environment = os.environ | {
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        "DOTNET_GENERATE_ASPNET_CERTIFICATE": "false", "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE": "true",
        "SYNCWATCH_CONTRACT_FIXTURES": str(ROOT / "contracts/fixtures/acceptance.json"),
    }
    executable = args.dotnet or shutil.which("dotnet")
    installed_version = None
    if executable is not None:
        installed = subprocess.run([executable, "--version"], cwd=ROOT, env=environment, text=True, capture_output=True)
        installed_version = installed.stdout.strip() if installed.returncode == 0 else None
    if installed_version != spec["sdkVersion"] and args.provision and not args.dotnet:
        directory = Path(os.environ.get("RUNNER_TEMP", str(ROOT / ".local/toolchains"))) / "syncwatch-server-sdk"
        executable = str(provision(spec, target, directory))
    if executable is None:
        raise ValueError("Supply the pinned .NET SDK or use --provision")
    actual = subprocess.check_output([executable, "--version"], cwd=ROOT, env=environment, text=True).strip()
    if actual != spec["sdkVersion"]:
        raise ValueError("Installed .NET SDK differs from the exact pin")
    output = ROOT / "artifacts/room-metadata/observed-contracts.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    environment["SYNCWATCH_ROOM_CONTRACT_OUTPUT"] = str(output)
    solution = "services/room-metadata/RoomMetadata.slnx"
    for command in (
        ["restore", solution, "--configfile", "NuGet.Config"],
        ["format", solution, "--no-restore", "--verify-no-changes"],
        ["build", solution, "--no-restore", "--configuration", "Debug"],
        ["run", "--project", "services/room-metadata/RoomMetadata.Tests", "--no-restore", "--no-build", "--configuration", "Debug"],
    ):
        subprocess.run([executable, *command], cwd=ROOT, env=environment, check=True)
    sys.path.insert(0, str(ROOT / "tools/contracts"))
    from check_contracts import Context, Registry
    registry = Registry(ROOT)
    observations = json.loads(output.read_text())
    if not observations or {value["schema"] for value in observations} != {"room-event", "room-snapshot", "room-selection"}:
        raise ValueError("Transport checks must produce actual room events, snapshots and selections")
    contexts = {}
    for observation in observations:
        value, kind = observation["value"], observation["schema"]
        if kind == "room-selection":
            registry.validate(kind, value)
        elif kind == "room-snapshot":
            registry.validate(kind, value)
            contexts[value["roomEpoch"]] = Context(roomEpoch=value["roomEpoch"], sequence=value["sequence"],
                watchGeneration=value["watchGeneration"], members={member["memberId"]: member["clientRunId"] for member in value["members"]})
        else:
            context = contexts[value["roomEpoch"]]
            registry.accept(kind, value, context)
            members = dict(context.members)
            if value["type"] == "member.bound":
                members[value["memberId"]] = value["clientRunId"]
            elif value["type"] == "member.left":
                members.pop(value["memberId"])
            contexts[value["roomEpoch"]] = Context(roomEpoch=value["roomEpoch"], sequence=value["sequence"],
                watchGeneration=value["watchGeneration"], members=members)
    print(f"Validated {len(observations)} actual metadata events/snapshots/selections against the pinned wire contracts")


if __name__ == "__main__":
    main()
