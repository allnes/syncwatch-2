"""Run Linux Kotlin domain and JVM boundaries; desktop acceptance remains separate."""

import json
from pathlib import Path
import platform
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/jvm"))
from build_support import java_environment
from jdk import home


def main():
    if (platform.system(), platform.machine()) != ("Linux", "x86_64"):
        raise ValueError("Linux checks require the actual Linux x64 target")
    jdk = home()
    output = ROOT / "artifacts/linux-boundary"
    output.mkdir(parents=True, exist_ok=True)
    classes = output / "classes"
    classes.mkdir(exist_ok=True)
    sources = sorted((ROOT / "packages/linux-playback/src").rglob("*.java"))
    sources += sorted((ROOT / "packages/ipc/jvm").rglob("*.java"))
    sources += [ROOT / "tools/native/tests/linux/BoundaryChecks.java"]
    environment = java_environment()
    for command in [
        [str(jdk / "bin/javac"), "-encoding", "UTF-8", "-Xlint:all", "-Werror", "-d", str(classes), *map(str, sources)],
        [str(jdk / "bin/java"), "-cp", str(classes), "BoundaryChecks"],
        [sys.executable, "tools/native/check_kotlin_domain.py"],
        [sys.executable, "tools/ci/check_platform_parity.py"],
    ]:
        subprocess.run(command, cwd=ROOT, env=environment, check=True)
    domain = json.loads((ROOT / "artifacts/kotlin-domain/linux-x64/report.json").read_text())
    if domain["hostTarget"] != "linux-x64" or not domain["sharedDomainAccepted"] or not domain["kotlinDomainCompiled"]:
        raise ValueError("Linux needs its actual compiled Kotlin domain proof")
    report = {"jvmBoundaryAccepted": True, "kotlinDomainCompiled": True, "sharedDomainAccepted": True, "applicationBuilt": False,
              "guiAccepted": False, "physicalOutputAccepted": False,
              "domain": domain,
              "blocked": json.loads((ROOT / "apps/linux/application.json").read_text())["blockedCapabilities"]}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Linux Kotlin domain/JVM checks passed; Compose application build and GUI acceptance remain incomplete")


if __name__ == "__main__":
    main()
