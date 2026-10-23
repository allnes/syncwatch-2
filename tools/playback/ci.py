"""Build, exercise and retain development playback consumers of the owned SDK."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import zipfile

from build import ROOT, check as native_check, runtime_environment
from consumers import check as consumer_check, run, verify_package


def target():
    return {("Darwin", "arm64"): "macos-arm64", ("Windows", "AMD64"): "windows-x64",
            ("Linux", "x86_64"): "linux-x64"}[(platform.system(), platform.machine())]


def provision():
    selected = target()
    (ROOT / "artifacts").mkdir(exist_ok=True)
    if selected == "linux-x64":
        subprocess.run([sys.executable, "tools/jvm/jdk.py", "--provision"], cwd=ROOT, check=True)
    elif selected == "windows-x64":
        spec = importlib.util.spec_from_file_location("playback_server_sdk", ROOT / "tools/server/check.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        specification = json.loads((ROOT / "tools/server/toolchains.json").read_text())
        temporary = Path(os.environ.get("RUNNER_TEMP", str(ROOT / ".local/toolchains"))) / "syncwatch-playback-sdk"
        executable = module.provision(specification, "win-x64", temporary)
        (ROOT / "artifacts/playback-sdk.json").write_text(json.dumps({"dotnet": str(executable)}) + "\n")


def candidate(package, output, bridge, binary_directory):
    selected = target()
    with zipfile.ZipFile(output / "candidate.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if selected == "macos-arm64":
            prefix = "SyncWatch.app/Contents/"
            archive.write(binary_directory / "SyncWatch", prefix + "MacOS/SyncWatch")
            archive.write(ROOT / "apps/apple/Resources/Info.plist", prefix + "Info.plist")
            media_prefix = prefix + "Frameworks/Media/"
        elif selected == "windows-x64":
            for path in sorted(binary_directory.rglob("*")):
                if path.is_file():
                    archive.write(path, "SyncWatch/" + path.relative_to(binary_directory).as_posix())
            archive.write(bridge, "SyncWatch/" + bridge.name)
            media_prefix = "SyncWatch/Media/"
        else:
            for path in sorted((output / "consumers/classes").rglob("*.class")):
                archive.write(path, "DevelopmentJVM/classes/" + path.relative_to(output / "consumers/classes").as_posix())
            for path in [bridge, output / "consumers/syncwatch_playback_jni.so"]:
                archive.write(path, "DevelopmentJVM/" + path.name)
            media_prefix = "DevelopmentJVM/Media/"
        for path in sorted(package.rglob("*")):
            if path.is_file():
                archive.write(path, media_prefix + path.relative_to(package).as_posix())
        archive.writestr("Sources/first-party.tar", subprocess.check_output(["git", "archive", "HEAD"], cwd=ROOT))
        archive.write(ROOT / "LICENSE", "LICENSE")
        archive.writestr("DEVELOPMENT.txt", "SyncWatch local playback development candidate.\n"
            "The Media directory includes the complete source, grants, recipe and integrity receipt.\n"
            "Use --local-playback with an absolute local movie path. Normal room activation remains gated.\n"
            "Windows requires the pinned developer .NET runtime. Linux contains a JNI development boundary, not a GUI.\n"
            "This is not a signed, authenticated or immutable release installation. Physical output is unqualified.\n")


def verify(dotnet=None, gui=False):
    selected = target()
    output = ROOT / "artifacts/playback" / selected
    output.mkdir(parents=True, exist_ok=True)
    package = ROOT / "artifacts/dependencies/libvlc" / selected / "payload"
    manifest = {"schemaVersion": 1, "source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "target": selected, "success": False, "physicalOutputAccepted": False,
                "releaseReady": False, "linuxGuiAccepted": False}
    try:
        receipt = verify_package(package)
        manifest["mediaSdk"] = receipt["sdk"]
        bridge = native_check(package, output / "native")
        env = runtime_environment(package, output / "native")
        binary_directory = None
        if selected == "macos-arm64":
            run(["swift", "build", "--package-path", "apps/apple", "-Xswiftc", "-warnings-as-errors"], output, "app-build", env)
            binary_directory = Path(subprocess.check_output(["swift", "build", "--package-path", "apps/apple", "--show-bin-path"], cwd=ROOT, text=True).strip())
            if gui:
                command = [str(binary_directory / "SyncWatch")]
        elif selected == "windows-x64":
            dotnet = dotnet or json.loads((ROOT / "artifacts/playback-sdk.json").read_bytes())["dotnet"]
            consumer_check(package, output / "consumers", dotnet=dotnet)
            run([dotnet, "build", "apps/windows/SyncWatch", "--configuration", "Debug", "--nologo",
                 "-m:1", "/p:UseSharedCompilation=false"], output, "app-build", env)
            binary_directory = ROOT / "apps/windows/SyncWatch/bin/Debug/net10.0-windows"
            if gui:
                command = [dotnet, str(binary_directory / "SyncWatch.dll"), "--playback-bridge", str(bridge)]
        else:
            consumer_check(package, output / "consumers", jdk_root=ROOT)
            # Both native objects must be adjacent in the relocated development candidate.
            bridge = output / "consumers" / bridge.name
        if gui and selected != "linux-x64":
            for mode in (["normal", "detach"] if selected == "windows-x64" else ["normal"]):
                report = output / (mode + "-app-proof.json")
                run([*command, "--local-playback", str(output / "native/owned-i420-pcm.avi"),
                     "--media-package", str(package), "--playback-report", str(report),
                     *(["--playback-detach-probe"] if mode == "detach" else [])], output, mode + "-app", env)
                proof = json.loads(report.read_bytes())
                if not proof.get("success") or not proof.get("actualNativeSurface") or proof["physicalOutputAccepted"]:
                    raise ValueError("Owned native app surface acceptance failed")
            manifest["nativeAppSurfaceAccepted"] = True
        else:
            manifest["nativeAppSurfaceAccepted"] = False
        candidate(package, output, bridge, binary_directory)
        manifest["success"] = True
    finally:
        (output / "acceptance.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        # Retain raw diagnostics even when the actual consumer fails.
        with zipfile.ZipFile(output.parent / (selected + ".zip"), "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(output.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(output).as_posix())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("provision", "check"))
    parser.add_argument("--dotnet")
    parser.add_argument("--gui", action="store_true", help="Require real AppKit/WPF surface acceptance on a GUI host")
    args = parser.parse_args()
    provision() if args.operation == "provision" else verify(args.dotnet, args.gui)
