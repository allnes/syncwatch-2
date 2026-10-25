"""Exercise the real language boundaries against an owned development media SDK."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from build import ROOT, build, runtime_environment


def run(command, output, name, env):
    (output / (name + "-command.json")).write_text(json.dumps(command, indent=2) + "\n")
    with (output / (name + ".log")).open("wb") as log:
        subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                       stdin=subprocess.DEVNULL, timeout=180, check=True)


def verify_package(package):
    # Integrity only. Authentication and immutable installation remain separate gates.
    report = json.loads((package / "build-report.json").read_bytes())
    files = {}
    for path in package.rglob("*"):
        if path.is_symlink():
            raise ValueError("Media receipt cannot contain symbolic links")
        if path.is_file() and path.relative_to(package).as_posix() != "build-report.json":
            with path.open("rb") as stream:
                files[path.relative_to(package).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    if files != report["files"]:
        raise ValueError("Media package differs from its complete receipt")
    return report


def check(package, output, dotnet=None, jdk_root=None):
    package, output = package.resolve(), output.resolve()
    context, bridge, _ = build(output)
    report = verify_package(package)
    if report["sdk"]["target"] != context.target:
        raise ValueError("Media target differs from the consumer")
    env = runtime_environment(package, output)
    from fixtures import create
    media = create(output)
    unicode_file = output / "owned Юникод 🎬.avi"
    shutil.copyfile(media, unicode_file)
    if dotnet:
        dotnet = str(Path(dotnet).resolve())
        actual = subprocess.check_output([dotnet, "--version"], cwd=ROOT, text=True).strip()
        if actual != json.loads((ROOT / "global.json").read_text())["sdk"]["version"]:
            raise ValueError("Playback consumer requires the pinned .NET SDK")
        run([dotnet, "build", "packages/windows-playback/SyncWatch.Playback.Probe", "--configuration", "Release",
             "--nologo", "-m:1", "/p:UseSharedCompilation=false"], output, "dotnet-build", env)
        probe = ROOT / "packages/windows-playback/SyncWatch.Playback.Probe/bin/Release/net10.0/SyncWatch.Playback.Probe.dll"
        run([dotnet, str(probe), str(bridge), str(package), str(unicode_file)], output, "dotnet-proof", env)
        proof = json.loads((output / "dotnet-proof.log").read_bytes())
        if not proof["success"] or proof["guiAccepted"] or proof["physicalOutputAccepted"]:
            raise ValueError("Native .NET acceptance failed")
    if jdk_root:
        if context.target != "linux-x64":
            raise ValueError("The JVM development boundary currently targets Linux")
        sys.path.insert(0, str(ROOT / "tools/jvm"))
        from jdk import home
        jdk = home(jdk_root)
        ambient = {"JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "JDK_JAVAC_OPTIONS", "_JAVA_OPTIONS", "CLASSPATH"}
        env = {key: value for key, value in env.items() if key.upper() not in ambient}
        jni = output / "syncwatch_playback_jni.so"
        context.run("playback-jni", [context.tool(context.env["CC"]), "-std=c11", "-shared", "-fPIC",
                    "-O2", "-g0", "-Wall", "-Wextra", "-Werror", "-I" + str(jdk / "include"),
                    "-I" + str(jdk / "include/linux"), "-I" + str(package / "include"),
                    str(ROOT / "packages/linux-playback/native/jni.c"),
                    str(ROOT / "packages/linux-playback/native/x11.c"),
                    str(bridge), "-ldl", "-Wl,-rpath,$ORIGIN", "-o", str(jni)])
        classes = output / "classes"
        classes.mkdir(exist_ok=True)
        sources = sorted((ROOT / "packages/linux-playback").rglob("*.java"))
        sources += sorted((ROOT / "packages/ipc/jvm").rglob("*.java"))
        run([str(jdk / "bin/javac"), "-encoding", "UTF-8", "-Xlint:all", "-Werror", "-d", str(classes),
             *map(str, sources)], output, "jvm-build", env)
        run([str(jdk / "bin/java"), "-cp", str(classes), "syncwatch.playback.MediaRuntimeProbe"],
            output, "jvm-integrity-proof", env)
        run([str(jdk / "bin/java"), "--enable-native-access=ALL-UNNAMED", "-cp", str(classes),
             "syncwatch.playback.PlaybackProbe", str(jni), str(package / "lib/libvlc.so.5"),
             report["sources"]["vlc"]["revision"], str(unicode_file)], output, "jvm-proof", env)
        proof = json.loads((output / "jvm-proof.log").read_bytes())
        if not proof["success"] or proof["guiAccepted"] or proof["physicalOutputAccepted"]:
            raise ValueError("Native JNI acceptance failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dotnet")
    parser.add_argument("--jdk-root", type=Path, help="Checkout containing the verified developer JDK")
    args = parser.parse_args()
    if not args.dotnet and not args.jdk_root:
        parser.error("Select at least one real language consumer")
    check(args.package, args.output, args.dotnet, args.jdk_root)
