"""Provision build SDKs explicitly, then validate and retain the owned helper."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from build import ROOT
from check import check
from helper_archive import write_archive


def target():
    return {("Darwin", "arm64"): "macos-arm64", ("Linux", "x86_64"): "linux-x64",
            ("Windows", "AMD64"): "windows-x64"}[(platform.system(), platform.machine())]


def provision():
    subprocess.run(["git", "submodule", "update", "--init", "--checkout", "--depth=1", "--", "3rdparty/fastjsonschema"], cwd=ROOT, check=True)
    if target() == "macos-arm64":
        return
    spec = importlib.util.spec_from_file_location("server_sdk", ROOT / "tools/server/check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    specification = json.loads((ROOT / "tools/server/toolchains.json").read_text(encoding="utf-8"))
    destination = Path(os.environ.get("RUNNER_TEMP", str(ROOT / ".local/toolchains"))) / "syncwatch-bridge-sdk"
    executable = module.provision(specification, "win-x64" if os.name == "nt" else "linux-x64", destination)
    (ROOT / "artifacts/bridge-sdk.json").write_text(json.dumps({"dotnet": str(executable)}) + "\n", encoding="utf-8")


def verify(dotnet=None):
    selected = target()
    directory = ROOT / "artifacts/helper" / selected
    check(ROOT / "artifacts/dependencies/syncplay-runtime" / selected / "payload", directory)
    binary = directory / "bin" / ("syncwatch-helper.exe" if os.name == "nt" else "syncwatch-helper")
    if selected == "macos-arm64":
        command = ["swift", "run", "--package-path", "packages/apple-bridge", "-Xswiftc", "-warnings-as-errors",
                   "BridgeProbe", str(binary), str(directory)]
    else:
        executable = dotnet or json.loads((ROOT / "artifacts/bridge-sdk.json").read_text(encoding="utf-8"))["dotnet"]
        actual = subprocess.check_output([executable, "--version"], cwd=ROOT, text=True).strip()
        if actual != json.loads((ROOT / "global.json").read_text())["sdk"]["version"]:
            raise ValueError("Bridge probe requires the pinned .NET SDK")
        command = [executable, "run", "--project", "packages/windows-bridge/SyncWatch.Bridge.Probe",
                   "--configuration", "Release", "--", str(binary), str(directory)]
    log = directory.parent / (selected + "-native.log")
    with log.open("wb") as stream:
        subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=180, check=True)
    if b"SYNCWATCH_NATIVE_BRIDGE_OK" not in log.read_bytes():
        raise ValueError("Native transport probe did not report success")
    write_archive(directory, [("native-probe.log", log),
        ("acceptance.json", directory.parent / (selected + "-acceptance.json"))],
        directory.parent / (selected + ".zip"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("provision", "check"))
    parser.add_argument("--dotnet")
    args = parser.parse_args()
    provision() if args.operation == "provision" else verify(args.dotnet)
