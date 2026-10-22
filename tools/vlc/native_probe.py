"""Compile a fresh native consumer and exercise the relocated owned media SDK."""

import json
import os
from pathlib import Path
import subprocess

from fixtures import create, encoded
from source_profile import ROOT


def verify(context, package):
    directory = context.work / "consumer"
    directory.mkdir()
    media = create(directory)
    suffix = ".exe" if context.target == "windows-x64" else ""
    executable = directory / ("vlc-probe" + suffix)
    libraries = package / ("bin" if context.target == "windows-x64" else "lib")
    libname = {"windows-x64": "libvlc.dll", "linux-x64": "libvlc.so.5", "macos-arm64": "libvlc.dylib"}[context.target]
    actual = libraries / libname
    if not actual.is_file():
        raise ValueError("Missing public libVLC runtime library")
    command = [context.tool(context.env["CC"]), "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I" + str(package / "include"), str(ROOT / "tools/vlc/probe.c"),
        "-L" + str(package / "lib"), "-lvlc", "-o", str(executable)]
    if context.target == "windows-x64":
        command.extend(["-static-libgcc", "-static-libstdc++"])
    else:
        command.append("-Wl,-rpath," + str(libraries))
        if context.target == "linux-x64":
            command.append("-ldl")
    context.run("consumer-compile", command)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DYLD_", "LD_", "VLC_"))}
    env["VLC_PLUGIN_PATH"] = str(libraries / "vlc/plugins")
    if context.target == "windows-x64":
        env["PATH"] = str(libraries) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    fixtures = {"i420-pcm": (media, {"videoCodec": "30323449", "audioCodec": "6c363173"})}
    fixtures.update(encoded(directory))
    results = {}
    for name, (fixture, metadata) in fixtures.items():
        output = directory / (name + "-proof.log")
        with output.open("wb") as log:
            process = subprocess.run([str(executable), str(fixture), str(actual)], env=env,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, timeout=60)
        if process.returncode:
            raise ValueError("Relocated media probe failed:\n" + output.read_text(errors="replace"))
        result = json.loads(output.read_text())
        expected = ["metadata", "decodeVideo", "decodeAudio", "play", "pause", "seekPixels", "resume", "stop", "reload", "release"]
        if (result.get("cases") != expected or result.get("ownedLibraryLoaded") is not True or
                result.get("physicalOutputAccepted") is not False or result.get("version") != "3.0.24" or
                any(result.get(key) != metadata[key] for key in ["videoCodec", "audioCodec"])):
            raise ValueError("Native media proof differs from its required behavior")
        results[name] = result
    return results
