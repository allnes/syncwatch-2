"""Source-owned Compose JVM runtime and its released annotation/collection inputs."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

import annotations
import concurrency
import jdk
import kotlin
import modules
import stdlib
import stdlib_sources
from build_support import digest, encoded, jar_bytes


ROOT = Path(__file__).resolve().parents[2]
COMPONENT = "compose-runtime"
CHANGES = (
    "SyncWatch Compose JVM runtime source profile\n"
    "All selected upstream Java/Kotlin files are compiled without changes.\n"
    "The common/intermediate/JVM source refinements are preserved.\n"
    "The verified Kotlin SDK Compose plugin runs only in the compiler process.\n"
    "JSpecify uses upstream's Java 8 source/target with JDK annotation APIs and\n"
    "its original Java 9 descriptor. The qualified runtime is JDK 21.\n"
    "This is an owned build profile, not an upstream Gradle artifact or equivalence claim.\n"
    "No desktop renderer, font, window, packaged JVM or application acceptance is included.\n"
).encode()


def profile_data():
    profile = json.loads((ROOT / "tools/jvm/compose_runtime.json").read_text())
    registry = json.loads((ROOT / "tools/dependencies/components.json").read_text())["components"]
    expected = dict(registry[concurrency.COMPONENT]["sources"])
    for source in profile["sources"].values():
        expected[source["path"]] = {k: source[k] for k in ("revision", "license", "notices", "requires", "exports")} | {"unusedSubmodules": {}}
        if set(source["exports"]) != set(source["files"]) or not set(source["notices"]) <= source["files"].keys():
            raise ValueError("Compose source exports differ from the complete source/notice inventory")
    selected = {name: [] for name in profile["sources"]}
    for module in profile["modules"]:
        selected[module["source"]].extend(module.get("java", []))
        selected[module["source"]].extend([module["module"]] if "module" in module else [])
        selected[module["source"]].extend(path for paths in module.get("fragments", {}).values() for path in paths)
    for name, paths in selected.items():
        code = {n for n in profile["sources"][name]["files"] if n.endswith((".kt", ".java"))}
        if len(paths) != len(set(paths)) or set(paths) != code:
            raise ValueError("Compose modules must own the exact selected code once")
    if (profile["schemaVersion"] != 1 or profile["profile"] != "desktop-jvm8-compose-v1"
            or profile["compilerVersion"] != kotlin.specification()["version"]
            or registry[COMPONENT]["sources"] != expected):
        raise ValueError("Compose source/compiler graph differs from the reviewed profile")
    kotlin.plugin_specification(kotlin.specification())
    return profile


def support(files, profile):
    return {"profile.json": encoded(profile), "CHANGES.txt": CHANGES} | {
        "originals/" + name + "/" + path: data
        for name, values in files.items() for path, data in values.items()}


def paths(payload, profile):
    parent = payload / "parent"
    return [parent / "runtime" / stdlib.BINARY, parent / "runtime/annotations" / annotations.BINARY,
            *[parent / binary for binary in concurrency.BINARIES.values()],
            *[payload / module["binary"] for module in profile["modules"]]]


def assemble(files, profile, payload, home, compiler):
    classpath = paths(payload, profile)[:4]
    with tempfile.TemporaryDirectory(prefix="compose-runtime-build-") as temporary:
        work = Path(temporary).resolve()
        for name, values in files.items():
            for filename, data in values.items():
                path = work / name / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        for module in profile["modules"]:
            name, source = module["name"], module["source"]
            directory = work / source
            classes = work / (name + "-classes")
            classes.mkdir()
            if "java" in module:
                # Match the original build.gradle: MODULE is part of NullMarked's target.
                # --release 8 would incorrectly hide that reviewed JDK annotation API.
                stdlib.javac(["-source", "8", "-target", "8", "-g:none", "-proc:none", "-encoding", "UTF-8",
                              "-d", str(classes), *[str(directory / p) for p in module["java"]]], work, home)
            else:
                fragments = {role: [directory / p for p in names] for role, names in module["fragments"].items()}
                flags = ["-jvm-target", "1.8", "-language-version", profile["languageVersion"], "-api-version", profile["languageVersion"],
                         "-module-name", name, "-jvm-default=enable", "-Xdont-warn-on-error-suppression",
                         "-opt-in=kotlin.contracts.ExperimentalContracts", "-opt-in=kotlin.ExperimentalMultiplatform"]
                modules.compile_module(fragments, module["refines"], classpath, classes, work, home, compiler, flags,
                                       allow_empty_platform=module["allowEmptyPlatform"], plugins=module["plugins"])
                java = [p for names in fragments.values() for p in names if p.suffix == ".java"]
                if java:
                    stdlib.javac(["--release", "8", "-g:none", "-proc:none", "-encoding", "UTF-8", "-cp",
                                  os.pathsep.join(map(str, [classes, *classpath])), "-d", str(classes), *map(str, java)], work, home)
            entries = {p.relative_to(classes).as_posix(): p.read_bytes() for p in classes.rglob("*") if p.is_file()}
            manifest = "Manifest-Version: 1.0\r\nImplementation-Version: " + module["version"] + "-syncwatch\r\n"
            if "module" in module:
                descriptor = work / (name + "-module")
                descriptor.mkdir()
                stdlib.javac(["--release", "9", "-g:none", "-proc:none", "--patch-module", "org.jspecify=" + str(classes),
                              "-d", str(descriptor), str(directory / module["module"])], work, home)
                entries["META-INF/versions/9/module-info.class"] = (descriptor / "module-info.class").read_bytes()
                manifest += "Multi-Release: true\r\n"
            entries |= {"META-INF/MANIFEST.MF": (manifest + "\r\n").encode(), "META-INF/CHANGES.txt": CHANGES,
                        "META-INF/UPSTREAM-NOTICES.txt": concurrency.source_notices(files, profile, source)}
            destination = payload / module["binary"]
            destination.write_bytes(jar_bytes(entries))
            classpath.append(destination)
            print("Compiled " + name, flush=True)


def verify(payload, files, profile, notices):
    names = {m["binary"] for m in profile["modules"]}
    actual = set()
    for path in payload.rglob("*"):
        if path.is_symlink():
            raise ValueError("Compose payload contains a symbolic link")
        if path.is_file() and path.relative_to(payload).parts[0] != "parent":
            actual.add(path.relative_to(payload).as_posix())
    if actual != names | {"compose-runtime-sources.jar"} | notices.keys():
        raise ValueError("Compose payload has missing or unexpected files")
    if any((payload / name).read_bytes() != data for name, data in notices.items()):
        raise ValueError("Compose original source notice changed")
    with zipfile.ZipFile(payload / "compose-runtime-sources.jar") as archive:
        expected = support(files, profile)
        if set(archive.namelist()) != set(expected) or any(archive.read(n) != data for n, data in expected.items()):
            raise ValueError("Compose original sources, notices or profile changed")
    pins = profile["expectedJars"][jdk.current_target()]
    if set(pins) != names:
        raise ValueError("Compose profile requires exact pins for every runtime artifact")
    for name, expected in pins.items():
        if digest((payload / name).read_bytes()) != expected:
            raise ValueError("Compose artifact differs from the reviewed compiler output: " + name)
    print("Verified six source-built Compose runtime modules and complete originals/notices")


def probe(payload, profile, home, compiler):
    classpath = paths(payload.resolve(), profile)
    with tempfile.TemporaryDirectory(prefix="compose-consumer-") as temporary:
        work = Path(temporary).resolve() / "Кино 映画"
        work.mkdir()
        classes = work / "classes"
        classes.mkdir()
        kotlin.compile(["-jvm-target", "1.8", "-Werror", "-classpath", os.pathsep.join(map(str, classpath)),
                        "-d", str(classes), str(ROOT / "tools/jvm/tests/ComposeRuntimeConsumer.kt")], work, home, compiler, plugins=("compose",))
        output = kotlin.java(["-cp", os.pathsep.join(map(str, [classes, *classpath])), "ComposeRuntimeConsumerKt", *map(str, classpath)], work, home)
        if "SYNCWATCH_COMPOSE_RUNTIME_OK" not in output:
            raise ValueError("Source-built Compose runtime consumer failed")
        print(output.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "verify"))
    parser.add_argument("--platform", choices=("linux-x64", "macos-arm64", "windows-x64"))
    args = parser.parse_args()
    profile = profile_data()
    home, compiler = jdk.home(), kotlin.home()
    archive = args.operation == "verify"
    directory = ROOT / "artifacts/dependencies" / COMPONENT / (args.platform or jdk.current_target()) if archive else Path(os.environ["SYNCWATCH_DEPENDENCY_SOURCES"])
    files = concurrency.read_sources(directory, profile, archive=archive)
    parent_profile = concurrency.profile_data()
    parent_files = concurrency.read_sources(directory, parent_profile, archive=archive)
    runtime_profile, source_profile = stdlib.profile_data()
    runtime_sources = {name: stdlib_sources.source_files(directory / (name + ".tar" if archive else source["path"]), source)
                       for name, source in source_profile["sources"].items()}
    annotation_profile, sdk = annotations.profile_data()
    annotation_files = annotations.source_files(directory / ("jvm-annotations.tar" if archive else annotation_profile["sourcePath"]), annotation_profile)
    all_sources = files | parent_files | runtime_sources | {"jvm-annotations": annotation_files}
    registry = json.loads((ROOT / "tools/dependencies/components.json").read_text())["components"]
    def notices_for(component):
        return {"notices/" + path.rsplit("/", 1)[1] + "/" + notice: all_sources[path.rsplit("/", 1)[1]][notice]
                for path, definition in registry[component]["sources"].items() for notice in definition["notices"]}
    notices = notices_for(COMPONENT)
    if args.operation == "build":
        if json.loads(os.environ["SYNCWATCH_DEPENDENCY_FLAGS"]) != {"profile": profile["profile"]}:
            raise ValueError("Unknown Compose runtime source profile")
        payload = Path(os.environ["SYNCWATCH_DEPENDENCY_OUTPUT"])
        parent = payload / "parent"
        parent.mkdir()
        environment = dict(os.environ, SYNCWATCH_DEPENDENCY_OUTPUT=str(parent),
                           SYNCWATCH_DEPENDENCY_FLAGS=json.dumps({"profile": parent_profile["profile"]}))
        subprocess.run([sys.executable, str(ROOT / "tools/jvm/concurrency.py"), "build"], env=environment, check=True)
        assemble(files, profile, payload, home, compiler)
        (payload / "compose-runtime-sources.jar").write_bytes(jar_bytes(support(files, profile)))
        for name, data in notices.items():
            path = payload / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    else:
        payload = directory / "payload"
    verify(payload, files, profile, notices)
    concurrency.verify(payload / "parent", parent_files, parent_profile, notices_for(concurrency.COMPONENT))
    stdlib.verify(payload / "parent/runtime", runtime_sources, source_profile, runtime_profile, annotation_files, annotation_profile, sdk["version"])
    if args.operation == "verify":
        probe(payload, profile, home, compiler)


if __name__ == "__main__":
    main()
