"""Compile only declared production Kotlin/Java inputs on Linux, using verified developer tools."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from receipts import ROOT, desktop_classpath, require_host


def build(arguments):
    require_host("linux-x64")
    sys.path.insert(0, str(ROOT / "tools/jvm"))
    import jdk
    import kotlin
    import stdlib
    from build_support import jar_bytes
    home = jdk.home(arguments.toolchain_root)
    compiler = kotlin.home(arguments.toolchain_root)
    classpath = desktop_classpath(arguments.desktop_sdk)
    manifest = json.loads((ROOT / "apps/linux/application.json").read_text())
    sources = sorted(path for owner in manifest["sources"] for path in (ROOT / owner).rglob("*")
                     if path.suffix in {".kt", ".java"})
    before = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    output = arguments.output.absolute()
    output.mkdir(exist_ok=False)
    try:
        with tempfile.TemporaryDirectory(prefix="sw-linux-application-", dir=output.parent) as temporary:
            work = Path(temporary)
            classes = work / "classes"
            classes.mkdir()
            stdlib.javac(["--release", "21", "-g:none", "-proc:none", "-encoding", "UTF-8", "-cp",
                          os.pathsep.join(map(str, classpath)), "-d", str(classes),
                          *[str(path) for path in sources if path.suffix == ".java"]], work, home)
            kotlin.compile(["-jvm-target", "21", "-Werror", "-classpath", os.pathsep.join(map(str, [classes, *classpath])),
                            "-d", str(classes), *[str(path) for path in sources if path.suffix == ".kt"]],
                           work, home, compiler, plugins=("compose",))
            if before != {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}:
                raise ValueError("Application sources changed during compilation")
            entries = {path.relative_to(classes).as_posix(): path.read_bytes() for path in classes.rglob("*") if path.is_file()}
            if "syncwatch/MainKt.class" not in entries:
                raise ValueError("Linux application entry point was not compiled")
            jar = output / "application.jar"
            jar.write_bytes(jar_bytes(entries))
            modules = subprocess.check_output([str(home / "bin/jdeps"), "--multi-release", "21", "--recursive",
                "--ignore-missing-deps", "--print-module-deps", "--class-path", os.pathsep.join(map(str, classpath)), str(jar)],
                text=True, timeout=120).strip().split(",")
            declared = json.loads((ROOT / "tools/application/jvm-profile.json").read_text())["moduleRoots"]
            if set(modules) - {"java.base", *declared}:
                raise ValueError("Application needs undeclared JVM modules: " + ",".join(sorted(set(modules) - {"java.base", *declared})))
            (output / "application-report.json").write_text(json.dumps({"schemaVersion": 1, "target": "linux-x64",
                "testSourcesIncluded": False, "sources": before, "jdkModules": modules,
                "sha256": hashlib.sha256(jar.read_bytes()).hexdigest()}, indent=2) + "\n")
    except BaseException:
        shutil.rmtree(output)
        raise
    print("Production Linux application built:", jar)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("toolchain-root", "desktop-sdk", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    build(parser.parse_args())
