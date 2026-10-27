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
from helper_archive import write_archive, write_origin


def target():
    return {("Darwin", "arm64"): "macos-arm64", ("Linux", "x86_64"): "linux-x64",
            ("Windows", "AMD64"): "windows-x64"}[(platform.system(), platform.machine())]


def provision(kotlin_runtime=None):
    if kotlin_runtime is not None and target() != "linux-x64":
        raise ValueError("The Kotlin bridge runtime is only used on Linux")
    subprocess.run(["git", "submodule", "update", "--init", "--checkout", "--depth=1", "--", "3rdparty/fastjsonschema"], cwd=ROOT, check=True)
    if target() == "macos-arm64":
        return
    if target() == "linux-x64":
        for tool in ("jdk", "kotlin"):
            subprocess.run([sys.executable, str(ROOT / "tools/jvm" / (tool + ".py")), "--provision"], cwd=ROOT, check=True)
        if kotlin_runtime is None:
            subprocess.run([sys.executable, "tools/dependencies/build.py", "build", "--component", "kotlin-stdlib",
                            "--platform", "linux-x64"], cwd=ROOT, check=True)
        return
    spec = importlib.util.spec_from_file_location("server_sdk", ROOT / "tools/server/check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    specification = json.loads((ROOT / "tools/server/toolchains.json").read_text(encoding="utf-8"))
    destination = Path(os.environ.get("RUNNER_TEMP", str(ROOT / ".local/toolchains"))) / "syncwatch-bridge-sdk"
    executable = module.provision(specification, "win-x64" if os.name == "nt" else "linux-x64", destination)
    (ROOT / "artifacts/bridge-sdk.json").write_text(json.dumps({"dotnet": str(executable)}) + "\n", encoding="utf-8")


def verify(dotnet=None, kotlin_runtime=None):
    selected = target()
    if dotnet is not None and selected != "windows-x64":
        raise ValueError("The C# bridge probe runs only on Windows")
    if kotlin_runtime is not None and selected != "linux-x64":
        raise ValueError("The Kotlin bridge runtime is only used on Linux")
    directory = ROOT / "artifacts/helper" / selected
    check(ROOT / "artifacts/dependencies/syncplay-runtime" / selected / "payload", directory)
    binary = directory / "bin" / ("syncwatch-helper.exe" if os.name == "nt" else "syncwatch-helper")
    if selected == "macos-arm64":
        command = ["swift", "run", "--package-path", "packages/macos-bridge", "-Xswiftc", "-warnings-as-errors",
                   "BridgeProbe", str(binary), str(directory)]
    elif selected == "windows-x64":
        executable = dotnet or json.loads((ROOT / "artifacts/bridge-sdk.json").read_text(encoding="utf-8"))["dotnet"]
        actual = subprocess.check_output([executable, "--version"], cwd=ROOT, text=True).strip()
        if actual != json.loads((ROOT / "global.json").read_text())["sdk"]["version"]:
            raise ValueError("Bridge probe requires the pinned .NET SDK")
        command = [executable, "run", "--project", "packages/windows-bridge/SyncWatch.Bridge.Probe",
                   "--configuration", "Release", "--", str(binary), str(directory)]
    log = directory.parent / (selected + "-native.log")
    with log.open("wb") as stream:
        if selected == "linux-x64":
            command = [sys.executable, str(ROOT / "tools/bridge/linux_probe.py"), str(binary), str(directory)]
            if kotlin_runtime is not None:
                command += ["--stdlib-artifact", str(kotlin_runtime)]
        subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=180, check=True)
    if b"SYNCWATCH_NATIVE_BRIDGE_OK" not in log.read_bytes():
        raise ValueError("Native transport probe did not report success")
    receipt = json.loads((directory / "helper-report.json").read_text(encoding="utf-8"))
    origin = write_origin(receipt, directory.parent / (selected + "-artifact-origin.json"),
                          run_id=os.environ.get("GITHUB_RUN_ID"), run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"))
    write_archive(directory, [("native-probe.log", log), ("origin.json", origin),
        ("acceptance.json", directory.parent / (selected + "-acceptance.json"))],
        directory.parent / (selected + ".zip"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("provision", "check"))
    parser.add_argument("--dotnet")
    parser.add_argument("--kotlin-runtime", type=Path, help="Owned kotlin-stdlib artifact directory (Linux only)")
    args = parser.parse_args()
    provision(args.kotlin_runtime) if args.operation == "provision" else verify(args.dotnet, args.kotlin_runtime)
