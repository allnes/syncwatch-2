"""Compile the real Kotlin pipe probe with the owned source-built runtime on Linux."""

import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def check(executable, runtime, artifact=None, toolchain_root=ROOT):
    if sys.platform != "linux":
        raise ValueError("The Kotlin helper probe requires Linux")
    sys.path.insert(0, str(ROOT / "tools/jvm"))
    import annotations
    import jdk
    import kotlin
    import stdlib
    import stdlib_sources

    artifact = artifact or ROOT / "artifacts/dependencies/kotlin-stdlib/linux-x64"
    payload = artifact / "payload"
    profile, sources = stdlib.profile_data()
    files = {name: stdlib_sources.source_files(artifact / (name + ".tar"), definition)
             for name, definition in sources["sources"].items()}
    annotation_profile, sdk = annotations.profile_data()
    annotation_files = annotations.source_files(artifact / "jvm-annotations.tar", annotation_profile)
    stdlib.verify(payload, files, sources, profile, annotation_files, annotation_profile, sdk["version"])
    home, compiler = jdk.home(toolchain_root), kotlin.home(toolchain_root)
    with tempfile.TemporaryDirectory(prefix="syncwatch-kotlin-pipe-") as temporary:
        work = Path(temporary)
        classes = work / "classes"
        classes.mkdir()
        binary = payload / stdlib.BINARY
        stdlib.javac(["--release", "21", "-encoding", "UTF-8", "-proc:none", "-Xlint:all", "-Werror",
                      "-d", str(classes), *map(str, sorted((ROOT / "packages/ipc/jvm").rglob("*.java")))], work, home)
        classpath = [classes, binary, payload / "annotations" / annotations.BINARY]
        kotlin.compile(["-jvm-target", "21", "-Werror", "-classpath", os.pathsep.join(map(str, classpath)),
                        "-d", str(classes), str(ROOT / "packages/linux-bridge/HelperTransport.kt"),
                        str(ROOT / "packages/linux-bridge/HelperProcess.kt"),
                        str(ROOT / "tools/bridge/NativeBridgeProbe.kt")], work, home, compiler)
        result = kotlin.java(["-cp", os.pathsep.join(map(str, classpath)),
                              "syncwatch.bridge.probe.NativeBridgeProbeKt", str(executable), str(runtime)], work, home)
        if "SYNCWATCH_NATIVE_BRIDGE_OK" not in result:
            raise ValueError("Kotlin process/pipe probe did not complete")
        print(result.strip())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("--stdlib-artifact", type=Path)
    args = parser.parse_args()
    check(args.executable.resolve(), args.runtime.resolve(), args.stdlib_artifact)
