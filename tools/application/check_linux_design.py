"""Check retained Design content and focus against the actual production Linux JAR."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from receipts import ROOT, desktop_classpath, renderer, require_host


def check(arguments):
    require_host("linux-x64")
    sys.path.insert(0, str(ROOT / "tools/jvm"))
    import jdk
    import kotlin

    application = arguments.application.resolve(strict=True)
    report = json.loads(application.with_name("application-report.json").read_text())
    if (report.get("target") != "linux-x64" or report.get("testSourcesIncluded") is not False
            or report.get("sha256") != hashlib.sha256(application.read_bytes()).hexdigest()
            or not report.get("sources")
            or any(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest
                   for name, digest in report["sources"].items())):
        raise ValueError("Design checks require the current, unmodified production application")
    renderer(arguments.renderer_package)
    classpath = [application, *desktop_classpath(arguments.desktop_sdk)]
    home = jdk.home(arguments.toolchain_root)
    compiler = kotlin.home(arguments.toolchain_root)
    with tempfile.TemporaryDirectory(prefix="syncwatch-retained-design-") as temporary:
        work = Path(temporary)
        classes = work / "classes"
        classes.mkdir()
        kotlin.compile(["-jvm-target", "21", "-Werror", "-Xfriend-paths=" + str(application),
                        "-classpath", os.pathsep.join(map(str, classpath)), "-d", str(classes),
                        str(ROOT / "packages/design/tests/linux/RetainedChecks.kt"),
                        str(ROOT / "packages/design/tests/linux/RenderChecks.kt")],
                       work, home, compiler, plugins=("compose",))
        output = kotlin.java(["-Djava.awt.headless=true",
                              "-Dskiko.library.path=" + str(arguments.renderer_package.resolve() / "runtime"),
                              "-cp", os.pathsep.join(map(str, [classes, *classpath])),
                              "syncwatch.design.tests.RetainedChecksKt"], work, home)
        if "SYNCWATCH_RETAINED_CONTENT_OK" not in output:
            raise ValueError("Retained Design content/focus verification failed")
        print(output.strip())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("application", "desktop-sdk", "renderer-package", "toolchain-root"):
        parser.add_argument("--" + name, required=True, type=Path)
    check(parser.parse_args())
