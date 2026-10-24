"""Source-owned desktop composition state, serialization and lifecycle runtime."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

import compose_runtime
import concurrency
import jdk
import kotlin
import modules
import stdlib
import stdlib_sources
from build_support import digest, encoded, jar_bytes


ROOT = Path(__file__).resolve().parents[2]
COMPONENT = "compose-state"
CHANGES = (
    "SyncWatch desktop composition state source profile\n"
    "Selected upstream sources, resources and Java 9 descriptors are unmodified.\n"
    "Common/intermediate/JVM source refinements are preserved.\n"
    "The verified Kotlin SDK Compose and serialization plugins are compiler-only.\n"
    "Swing supplies the real desktop Main dispatcher and event-thread affinity.\n"
    "State recreation is in-process; this profile introduces no durable storage format.\n"
    "This is an owned build profile, not the upstream Gradle artifacts or an equivalence claim.\n"
    "No renderer, native window, font or packaged application acceptance is included.\n"
).encode()
OPT_INS = ["kotlin.contracts.ExperimentalContracts", "kotlin.ExperimentalMultiplatform",
           "kotlinx.serialization.InternalSerializationApi", "kotlinx.serialization.ExperimentalSerializationApi",
           "kotlinx.coroutines.InternalCoroutinesApi", "kotlinx.coroutines.ExperimentalCoroutinesApi"]


def profile_data():
    profile = json.loads((ROOT / "tools/jvm/compose_state.json").read_text())
    registry = json.loads((ROOT / "tools/dependencies/components.json").read_text())["components"]
    expected = dict(registry[compose_runtime.COMPONENT]["sources"])
    for source in profile["sources"].values():
        expected[source["path"]] = {k: source[k] for k in ("revision", "license", "notices", "requires", "exports")} | {"unusedSubmodules": {}}
        if set(source["exports"]) != set(source["files"]) or not set(source["notices"]) <= source["files"].keys():
            raise ValueError("Composition state exports differ from the complete source/notice inventory")
    selected = {name: [] for name in profile["sources"]}
    for module in profile["modules"]:
        selected[module["source"]].extend(module.get("java", []))
        selected[module["source"]].extend([module["module"]["path"]] if "module" in module else [])
        selected[module["source"]].extend(path for paths in module.get("fragments", {}).values() for path in paths)
    for name, paths_ in selected.items():
        code = {n for n in profile["sources"][name]["files"] if n.endswith((".kt", ".java"))}
        if len(paths_) != len(set(paths_)) or set(paths_) != code:
            raise ValueError("Composition state modules must own the exact selected code once")
    if (profile["schemaVersion"] != 1 or profile["profile"] != "desktop-state-jvm8-v1"
            or profile["compilerVersion"] != kotlin.specification()["version"]
            or registry[COMPONENT]["sources"] != expected):
        raise ValueError("Composition state source/compiler graph differs from the reviewed profile")
    kotlin.plugin_specification(kotlin.specification())
    return profile


def support(files, profile):
    return {"profile.json": encoded(profile), "CHANGES.txt": CHANGES} | {
        "originals/" + name + "/" + path: data
        for name, values in files.items() for path, data in values.items()}


def paths(payload, profile):
    return [*compose_runtime.paths(payload / "parent", compose_runtime.profile_data()),
            *[payload / module["binary"] for module in profile["modules"]]]


def assemble(files, profile, payload, home, compiler):
    classpath = compose_runtime.paths(payload / "parent", compose_runtime.profile_data())
    with tempfile.TemporaryDirectory(prefix="compose-state-build-") as temporary:
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
                stdlib.javac(["--release", "8", "-g:none", "-proc:none", "-encoding", "UTF-8",
                              "-cp", os.pathsep.join(map(str, classpath)), "-d", str(classes),
                              *[str(directory / p) for p in module["java"]]], work, home)
            else:
                fragments = {role: [directory / p for p in names] for role, names in module["fragments"].items()}
                language = module["languageVersion"]
                flags = ["-jvm-target", "1.8", "-language-version", language, "-api-version", language,
                         "-module-name", name, "-jvm-default=enable", "-Xdont-warn-on-error-suppression",
                         *["-opt-in=" + marker for marker in OPT_INS]]
                modules.compile_module(fragments, module["refines"], classpath, classes, work, home, compiler, flags,
                                       allow_empty_platform=module["allowEmptyPlatform"], plugins=module["plugins"])
                java = [p for names in fragments.values() for p in names if p.suffix == ".java"]
                if java:
                    stdlib.javac(["--release", "8", "-g:none", "-proc:none", "-encoding", "UTF-8", "-cp",
                                  os.pathsep.join(map(str, [classes, *classpath])), "-d", str(classes), *map(str, java)], work, home)
            entries = {p.relative_to(classes).as_posix(): p.read_bytes() for p in classes.rglob("*") if p.is_file()}
            manifest = {"Manifest-Version": "1.0", "Implementation-Version": module["version"] + "-syncwatch"}
            manifest.update(module.get("manifest", {}))
            if "module" in module:
                descriptor = work / (name + "-module")
                descriptor.mkdir()
                stdlib.javac(["--release", "9", "-g:none", "-proc:none", "-encoding", "UTF-8",
                              "--module-path", os.pathsep.join(map(str, classpath)), "--patch-module",
                              module["module"]["name"] + "=" + str(classes), "-d", str(descriptor),
                              str(directory / module["module"]["path"])], work, home)
                entries["META-INF/versions/9/module-info.class"] = (descriptor / "module-info.class").read_bytes()
                manifest["Multi-Release"] = "true"
            entries |= {destination: files[source][original] for destination, original in module.get("resources", {}).items()}
            entries |= {"META-INF/MANIFEST.MF": ("".join(k + ": " + v + "\r\n" for k, v in manifest.items()) + "\r\n").encode(),
                        "META-INF/CHANGES.txt": CHANGES,
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
            raise ValueError("Composition state payload contains a symbolic link")
        if path.is_file() and path.relative_to(payload).parts[0] != "parent":
            actual.add(path.relative_to(payload).as_posix())
    if actual != names | {"compose-state-sources.jar"} | notices.keys():
        raise ValueError("Composition state payload has missing or unexpected files")
    if any((payload / name).read_bytes() != data for name, data in notices.items()):
        raise ValueError("Composition state original source notice changed")
    with zipfile.ZipFile(payload / "compose-state-sources.jar") as archive:
        expected = support(files, profile)
        if (len(archive.namelist()) != len(expected) or set(archive.namelist()) != set(expected)
                or any(archive.read(n) != data for n, data in expected.items())):
            raise ValueError("Composition state original sources, notices or profile changed")
    pins = profile["expectedJars"][jdk.current_target()]
    if set(pins) != names:
        raise ValueError("Composition state profile requires exact pins for every runtime artifact")
    for name, expected in pins.items():
        if digest((payload / name).read_bytes()) != expected:
            raise ValueError("Composition state artifact differs from the reviewed compiler output: " + name)
    print("Verified nine source-built composition state modules and complete originals/notices")


def probe(payload, profile, home, compiler):
    classpath = paths(payload.resolve(), profile)
    with tempfile.TemporaryDirectory(prefix="compose-state-consumer-") as temporary:
        work = Path(temporary).resolve() / "Кино 映画"
        work.mkdir()
        classes = work / "classes"
        classes.mkdir()
        sources = sorted((ROOT / "packages/linux-state/src").rglob("*.kt"))
        kotlin.compile(["-jvm-target", "1.8", "-Werror", "-classpath", os.pathsep.join(map(str, classpath)),
                        "-d", str(classes), *map(str, sources), str(ROOT / "tools/jvm/tests/ComposeStateConsumer.kt")],
                       work, home, compiler, plugins=("compose", "serialization"))
        output = kotlin.java(["-Djava.awt.headless=true", "-cp", os.pathsep.join(map(str, [classes, *classpath])),
                              "ComposeStateConsumerKt", *map(str, classpath)], work, home)
        if "SYNCWATCH_COMPOSE_STATE_OK" not in output:
            raise ValueError("Source-built composition state consumer failed")
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
    for name, source in profile["sources"].items():
        unheaded = {n for n, data in files[name].items() if n.endswith((".kt", ".java")) and stdlib_sources.apache_header(data) is None}
        if unheaded != set(source["repositoryLicensedFiles"]):
            raise ValueError("Composition state source headers differ from the reviewed repository grant")
    parent_sources = compose_runtime.original_sources(directory, archive=archive)
    notices = compose_runtime.original_notices(COMPONENT, parent_sources | files)
    if args.operation == "build":
        if json.loads(os.environ["SYNCWATCH_DEPENDENCY_FLAGS"]) != {"profile": profile["profile"]}:
            raise ValueError("Unknown composition state source profile")
        payload = Path(os.environ["SYNCWATCH_DEPENDENCY_OUTPUT"])
        parent = payload / "parent"
        parent.mkdir()
        environment = dict(os.environ, SYNCWATCH_DEPENDENCY_OUTPUT=str(parent),
                           SYNCWATCH_DEPENDENCY_FLAGS=json.dumps({"profile": compose_runtime.profile_data()["profile"]}))
        subprocess.run([sys.executable, str(ROOT / "tools/jvm/compose_runtime.py"), "build"], env=environment, check=True)
        assemble(files, profile, payload, home, compiler)
        (payload / "compose-state-sources.jar").write_bytes(jar_bytes(support(files, profile)))
        for name, data in notices.items():
            path = payload / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    else:
        payload = directory / "payload"
    compose_runtime.verify_runtime(payload / "parent", parent_sources)
    verify(payload, files, profile, notices)
    if args.operation == "verify":
        probe(payload, profile, home, compiler)


if __name__ == "__main__":
    main()
