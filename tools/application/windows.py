"""Publish a WPF apphost using a private SDK-provided platform framework runtime."""

import json
import os
from pathlib import Path
import shutil
import subprocess

from candidate_tree import Component
from receipts import ROOT, require_host


def runtime_parts(sdk, version):
    folders = [sdk / path for path in ("host/fxr", "shared/Microsoft.NETCore.App", "shared/Microsoft.WindowsDesktop.App")]
    if not all((folder / version).is_dir() for folder in folders):
        raise ValueError("Pinned Windows SDK lacks the exact declared platform runtimes")
    return [(folder / version, folder.relative_to(sdk).as_posix() + "/" + version) for folder in folders]


def prepare(arguments, work):
    require_host("windows-x64")
    dotnet = arguments.dotnet.resolve(strict=True)
    expected = json.loads((ROOT / "tools/native/toolchains.json").read_text())["windows"]
    if subprocess.check_output([str(dotnet), "--version"], cwd=ROOT, text=True).strip() != expected["dotnetSdk"]:
        raise ValueError("Windows packaging requires the exact declared SDK")
    parts = runtime_parts(dotnet.parent, expected["dotnetRuntime"])
    application = work / "application"
    environment = os.environ | {"DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER": "1",
                               "MSBUILDDISABLENODEREUSE": "1"}
    command = [str(dotnet), "publish", str(arguments.application), "--no-restore", "--configuration", "Debug",
               "--output", str(application), "--disable-build-servers", "-v:q",
               "-p:BuildInParallel=false", "-p:UseSharedCompilation=false",
               "-p:AppHostRelativeDotNet=Runtime", "-p:AppHostDotNetSearch=AppRelative"]
    process = subprocess.Popen(command, cwd=ROOT, env=environment, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    try:
        status = process.wait(timeout=180)
        if status:
            raise subprocess.CalledProcessError(status, command)
    except BaseException:
        if process.poll() is None:
            # Terminate only this invocation's process tree; never shut down unrelated SDK servers.
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False, timeout=15)
            process.wait(timeout=15)
        raise
    required = {"SyncWatch.exe", "SyncWatch.dll", "SyncWatch.Domain.dll", "SyncWatch.Room.dll",
                "SyncWatch.Library.dll", "SyncWatch.Playback.dll", "SyncWatch.Bridge.dll",
                "SyncWatch.deps.json", "SyncWatch.runtimeconfig.json"}
    if not all((application / name).is_file() for name in required):
        raise ValueError("Published application dependency closure is incomplete")
    bridge = arguments.bridge.resolve(strict=True)
    shutil.copy2(bridge, application / "syncwatch_playback.dll")
    runtime = application / "Runtime"
    runtime.mkdir()
    shutil.copy2(dotnet, runtime / "dotnet.exe")
    for name in ("LICENSE.txt", "ThirdPartyNotices.txt"):
        shutil.copy2(dotnet.parent / name, runtime / name)
    shutil.copy2(ROOT / "LICENSE", application / "LICENSE")
    return [Component(application, "SyncWatch"),
            Component(arguments.media_package, "SyncWatch/Media"),
            Component(arguments.helper_package, "SyncWatch/Syncplay"),
            *[Component(source, "SyncWatch/Runtime/" + relative) for source, relative in parts]]
