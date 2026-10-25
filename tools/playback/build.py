"""Compile the first-party playback ABI with the selected native media SDK tools."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/vlc"))
from build_context import BuildContext
from source_profile import profile_data


def build(directory):
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    context = BuildContext(directory / "sdk", profile_data()["sourceDateEpoch"])
    suffix = {"macos-arm64": ".dylib", "windows-x64": ".dll", "linux-x64": ".so"}[context.target]
    library = directory / ("syncwatch_playback" + suffix)
    sources = ROOT / "packages/playback-native/src"
    common = [context.tool(context.env["CC"]), "-std=c11", "-O2", "-g0", "-Wall", "-Wextra", "-Werror"]
    command = [*common, "-shared", "-fvisibility=hidden", str(sources / "library.c"), str(sources / "playback.c"), "-o", str(library)]
    if context.target == "windows-x64":
        command += ["-static-libgcc"]
    else:
        command += ["-fPIC", "-lm"]
        if context.target == "macos-arm64":
            command += ["-Wl,-install_name,@rpath/" + library.name]
        else:
            command += ["-Wl,-soname," + library.name]
        if context.target == "linux-x64":
            command += ["-ldl"]
    context.run("playback-abi", command)
    executable = directory / ("playback-probe.exe" if os.name == "nt" else "playback-probe")
    command = [*common, "-D_POSIX_C_SOURCE=200809L", str(ROOT / "tools/playback/native_probe.c"), str(library), "-o", str(executable)]
    if context.target == "windows-x64":
        command += ["-static-libgcc"]
    else:
        command += ["-Wl,-rpath," + str(directory)]
    context.run("playback-probe", command)
    return context, library, executable


def runtime_environment(package, output):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DYLD_", "LD_", "VLC_"))}
    if os.name == "nt":
        env["PATH"] = str(output) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    if sys.platform == "linux":
        env["FONTCONFIG_FILE"] = str(package / "share/fonts/fonts.conf")
        env["FONTCONFIG_PATH"] = str(package / "share/fonts")
        env["PULSE_CLIENTCONFIG"] = str(package / "share/pulse/client.conf")
        env["XDG_CACHE_HOME"] = str(output / "font-cache")
    return env


def check(package, output):
    context, library, executable = build(output)
    from fixtures import create
    media = create(output)
    libvlc = package / ("bin/libvlc.dll" if os.name == "nt" else "lib/libvlc.dylib" if sys.platform == "darwin" else "lib/libvlc.so.5")
    env = runtime_environment(package, output)
    with (output / "native-proof.json").open("wb") as log, (output / "native-stderr.log").open("wb") as errors:
        subprocess.run([str(executable), str(libvlc.resolve()), profile_data()["sources"]["vlc"]["revision"], str(media.resolve())],
                       stdin=subprocess.DEVNULL, stdout=log, stderr=errors, env=env, timeout=180, check=True)
    proof = json.loads((output / "native-proof.json").read_bytes())
    assert proof["abiBytes"] == 80 and proof["repeatedRelease"] and proof["physicalOutputAccepted"] is False
    print(json.dumps(proof, sort_keys=True))
    return library


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check(args.package.resolve(), args.output.resolve())
