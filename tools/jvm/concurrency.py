"""Offline JVM concurrency runtime from pinned original Kotlin/Java sources."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

import annotations
import jdk
import kotlin
import modules
import stdlib
import stdlib_sources
from build_support import digest, encoded, jar_bytes, run, tools


ROOT = Path(__file__).resolve().parents[2]
COMPONENT = "kotlinx-concurrency"
BINARIES = {"kotlinx-atomicfu": "atomicfu-0.32.1-syncwatch.jar",
            "kotlinx-coroutines": "kotlinx-coroutines-core-1.11.0-syncwatch.jar"}
EDGES = [("concurrent", "common"), ("jvm", "concurrent")]
OPT_INS = ["kotlin.ExperimentalMultiplatform", "kotlin.experimental.ExperimentalTypeInference",
           "kotlinx.coroutines.DelicateCoroutinesApi", "kotlinx.coroutines.ExperimentalCoroutinesApi",
           "kotlinx.coroutines.ObsoleteCoroutinesApi", "kotlinx.coroutines.InternalCoroutinesApi",
           "kotlinx.coroutines.FlowPreview"]


def profile_data():
    profile = json.loads((ROOT / "tools/jvm/concurrency.json").read_text())
    component = json.loads((ROOT / "tools/dependencies/components.json").read_text())["components"][COMPONENT]
    base = json.loads((ROOT / "tools/dependencies/components.json").read_text())["components"]["kotlin-stdlib"]
    expected = dict(base["sources"])
    for source in profile["sources"].values():
        entry = {k: source[k] for k in ("revision", "license", "notices", "exports")}
        entry |= {"requires": source["requires"], "unusedSubmodules": {}}
        expected[source["path"]] = entry
        if set(source["exports"]) != set(source["files"]) or not set(source["notices"]) <= source["files"].keys():
            raise ValueError("Concurrency source exports differ from the complete file/notice inventory")
        roles = [n for values in source["roles"].values() for n in values]
        if len(roles) != len(set(roles)) or not set(roles) <= source["files"].keys():
            raise ValueError("Concurrency source roles overlap or leave the reviewed inventory")
    if (component["sources"] != expected or profile["compilerVersion"] != kotlin.specification()["version"]
            or profile["profile"] != "jvm8-untransformed-module9-v1"):
        raise ValueError("Concurrency source/compiler graph differs from its reviewed profile")
    return profile


def read_sources(directory, profile, archive=False):
    return {name: stdlib_sources.source_files(directory / (name + ".tar" if archive else source["path"]), source)
            for name, source in profile["sources"].items()}


def support(files, profile):
    entries = {"profile.json": encoded(profile)}
    for name, source in profile["sources"].items():
        for path, content in files[name].items():
            entries["originals/" + name + "/" + path] = content
    entries["CHANGES.txt"] = (
        "SyncWatch JVM concurrency source profile\n"
        "All selected upstream Kotlin/Java source files are compiled without modifications.\n"
        "Atomicfu calls retain the original JVM atomic runtime; no bytecode/IR transformer runs.\n"
        "Common, concurrent and JVM fragments retain their original expect/actual refinements.\n"
        "DebugProbesKt.bin is rebuilt from the original integration-test source; the upstream\n"
        "precompiled resource is not a build input. Java 9 descriptors are built from original source.\n"
        "Android SuppressLint and Animal Sniffer are source-built compile-time annotations only.\n"
        "This is an owned build profile, not the upstream Gradle artifact or an equivalence claim.\n"
    ).encode()
    return entries


def source_notices(files, profile, name):
    source = profile["sources"][name]
    content = (name + "\nSource revision: " + source["revision"] + "\nSelected license: " + source["license"] + "\n\n").encode()
    for path in source["notices"]:
        content += ("\nOriginal " + path + ":\n").encode() + files[name][path] + b"\n"
    headers = {data.split(b"*/", 1)[0] + b"*/" for data in files[name].values() if data.lstrip().startswith(b"/*")}
    return content + b"\nOriginal source headers:\n" + b"\n\n".join(sorted(headers))


def assemble(files, profile, payload, home, compiler):
    runtime = payload / "runtime"
    classpath = [runtime / stdlib.BINARY, runtime / "annotations" / annotations.BINARY]
    with tempfile.TemporaryDirectory(prefix="concurrency-build-") as temporary:
        work = Path(temporary).resolve()
        for name, values in files.items():
            for filename, data in values.items():
                path = work / name / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        java_classes = work / "compile-annotations"
        java_classes.mkdir()
        java_sources = [work / name / path for name, source in profile["sources"].items()
                        for path in source["roles"].get("java", [])]
        stdlib.javac(["--release", "8", "-g:none", "-proc:none", "-encoding", "UTF-8", "-d", str(java_classes),
                      *map(str, java_sources)], work, home)
        java_entries = {p.relative_to(java_classes).as_posix(): p.read_bytes() for p in java_classes.rglob("*.class")}
        for name in ("android-platform-annotations", "animal-sniffer-annotations"):
            java_entries["META-INF/" + name + "-NOTICES.txt"] = source_notices(files, profile, name)
        (payload / "compile-annotations.jar").write_bytes(jar_bytes(java_entries))
        for name, binary in BINARIES.items():
            source = profile["sources"][name]
            classes = work / name / "classes"
            classes.mkdir()
            fragments = {role: [work / name / n for n in source["roles"][role]] for role in ("common", "concurrent", "jvm")}
            flags = ["-jvm-target", "1.8", "-language-version", profile["languageVersion"], "-api-version", profile["languageVersion"],
                     "-module-name", "atomicfu" if name == "kotlinx-atomicfu" else "kotlinx-coroutines-core",
                     "-Xdont-warn-on-error-suppression"]
            if name == "kotlinx-atomicfu":
                flags += ["-opt-in=kotlinx.atomicfu.locks.ExperimentalThreadBlockingApi"]
            else:
                flags += ["-progressive", *["-opt-in=" + marker for marker in OPT_INS]]
            modules.compile_module(fragments, EDGES, [*classpath, java_classes], classes, work, home, compiler, flags)
            entries = {p.relative_to(classes).as_posix(): p.read_bytes() for p in classes.rglob("*") if p.is_file()}
            for resource in source["roles"].get("resources", []):
                relative = resource.split("/resources/", 1)[1]
                entries[relative] = files[name][resource]
            entries["META-INF/UPSTREAM-NOTICES.txt"] = source_notices(files, profile, name)
            entries["META-INF/CHANGES.txt"] = support(files, profile)["CHANGES.txt"]
            manifest = "Manifest-Version: 1.0\r\nMulti-Release: true\r\nImplementation-Version: " + profile["versions"]["atomicfu" if name == "kotlinx-atomicfu" else "coroutines"] + "-syncwatch\r\n"
            if name == "kotlinx-coroutines":
                # Compile the original replacement class with access to its original module.
                provisional = work / "core-before-module.jar"
                provisional.write_bytes(jar_bytes(entries))
                probes = work / "probes"
                probes.mkdir()
                kotlin.compile(["-jvm-target", "1.8", "-language-version", profile["languageVersion"],
                                "-api-version", profile["languageVersion"], "-Xallow-kotlin-package",
                                "-Xfriend-paths=" + str(provisional), "-classpath", os.pathsep.join(map(str, [*classpath, provisional])),
                                "-d", str(probes), str(work / name / source["roles"]["probe"][0])], work, home, compiler)
                entries["DebugProbesKt.bin"] = (probes / "kotlin/coroutines/jvm/internal/DebugProbesKt.class").read_bytes()
                manifest += "Premain-Class: kotlinx.coroutines.debug.internal.AgentPremain\r\nCan-Retransform-Classes: true\r\n"
            module_classes = work / name / "module"
            module_classes.mkdir()
            module_name = "kotlinx.atomicfu" if name == "kotlinx-atomicfu" else "kotlinx.coroutines.core"
            stdlib.javac(["--release", "9", "-g:none", "-proc:none", "-encoding", "UTF-8",
                          "--module-path", os.pathsep.join(map(str, classpath)), "--patch-module", module_name + "=" + str(classes),
                          "-d", str(module_classes), str(work / name / source["roles"]["module"][0])], work, home)
            entries["META-INF/versions/9/module-info.class"] = (module_classes / "module-info.class").read_bytes()
            entries["META-INF/MANIFEST.MF"] = (manifest + "\r\n").encode()
            destination = payload / binary
            destination.write_bytes(jar_bytes(entries))
            classpath.append(destination)


def verify(payload, files, profile, notices):
    names = {*BINARIES.values(), "compile-annotations.jar", "concurrency-sources.jar"}
    actual = set()
    for path in payload.rglob("*"):
        if path.is_symlink():
            raise ValueError("Concurrency payload contains a symbolic link")
        if path.is_file() and path.relative_to(payload).parts[0] != "runtime":
            actual.add(path.relative_to(payload).as_posix())
    if actual != names | notices.keys():
        raise ValueError("Concurrency payload has missing or unexpected files: " + str(sorted(actual ^ (names | notices.keys()))))
    if any((payload / name).read_bytes() != data for name, data in notices.items()):
        raise ValueError("Concurrency original source notice changed")
    with zipfile.ZipFile(payload / "concurrency-sources.jar") as archive:
        expected = support(files, profile)
        if set(archive.namelist()) != set(expected) or any(archive.read(n) != b for n, b in expected.items()):
            raise ValueError("Concurrency original sources, notices or profile changed")
    pins = profile["expectedJars"][jdk.current_target()]
    if set(pins) != names - {"concurrency-sources.jar"}:
        raise ValueError("Concurrency profile requires exact binary and compile-annotation pins")
    for name, expected in pins.items():
        if digest((payload / name).read_bytes()) != expected:
            raise ValueError("Concurrency artifact differs from the reviewed compiler output: " + name)
    for binary in BINARIES.values():
        with zipfile.ZipFile(payload / binary) as archive:
            for name in ("META-INF/UPSTREAM-NOTICES.txt", "META-INF/CHANGES.txt", "META-INF/versions/9/module-info.class"):
                if not archive.read(name):
                    raise ValueError("Concurrency artifact lacks original notices or module descriptor")
    print("Verified source-built concurrency artifacts, complete originals/notices and original Java 9 modules")


def probe(payload, home, compiler):
    payload = payload.resolve()
    paths = [payload / "runtime" / stdlib.BINARY, payload / "runtime/annotations" / annotations.BINARY,
             *[payload / binary for binary in BINARIES.values()]]
    with tempfile.TemporaryDirectory(prefix="concurrency-consumer-") as temporary:
        work = Path(temporary).resolve() / "Кино 映画"
        work.mkdir()
        classes = work / "classes"
        classes.mkdir()
        # Keep the native Windows launcher's agent argument ASCII, as for tool
        # argfiles. Runtime classpaths still name the verified original payload.
        (work / "debug-agent.jar").write_bytes((payload / BINARIES["kotlinx-coroutines"]).read_bytes())
        kotlin.compile(["-classpath", os.pathsep.join(map(str, paths)), "-jvm-target", "1.8", "-Werror", "-d", str(classes),
                        str(ROOT / "tools/jvm/tests/ConcurrencyConsumer.kt")], work, home, compiler)
        for mode, launch in [
            ("ordinary", ["-cp", os.pathsep.join(map(str, [classes, *paths]))]),
            ("agent", ["-javaagent:debug-agent.jar", "-cp", os.pathsep.join(map(str, [classes, *paths]))]),
            ("modules", ["--module-path", os.pathsep.join(map(str, paths)), "--add-modules", "kotlinx.coroutines.core,org.jetbrains.annotations", "-cp", str(classes)])
        ]:
            output = kotlin.java([*launch, "ConcurrencyConsumerKt", *map(str, paths), mode], work, home)
            if "SYNCWATCH_CONCURRENCY_OK" not in output:
                raise ValueError("Source-built concurrency consumer failed")
            print(output.strip())
        dependencies = run([tools(home)["jdeps"], "--multi-release", "9", "--module-path",
                            os.pathsep.join(map(str, paths)), "--class-path", str(payload / "compile-annotations.jar"),
                            "--print-module-deps", "--module", "kotlinx.coroutines.core"], work).strip()
        if dependencies != "java.base,java.instrument,jdk.unsupported,kotlinx.atomicfu":
            raise ValueError("Concurrency runtime contains an undeclared dependency: " + dependencies)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "verify"))
    parser.add_argument("--platform", choices=("linux-x64", "macos-arm64", "windows-x64"))
    args = parser.parse_args()
    profile = profile_data()
    home, compiler = jdk.home(), kotlin.home()
    archive = args.operation == "verify"
    directory = ROOT / "artifacts/dependencies" / COMPONENT / (args.platform or jdk.current_target()) if archive else Path(os.environ["SYNCWATCH_DEPENDENCY_SOURCES"])
    files = read_sources(directory, profile, archive=archive)
    stdlib_profile, source_profile = stdlib.profile_data()
    runtime_sources = {name: stdlib_sources.source_files(directory / (name + ".tar" if archive else definition["path"]), definition)
                       for name, definition in source_profile["sources"].items()}
    annotation_profile, sdk = annotations.profile_data()
    annotation_files = annotations.source_files(directory / ("jvm-annotations.tar" if archive else annotation_profile["sourcePath"]), annotation_profile)
    all_sources = files | runtime_sources | {"jvm-annotations": annotation_files}
    component = json.loads((ROOT / "tools/dependencies/components.json").read_text())["components"][COMPONENT]
    notices = {"notices/" + path.rsplit("/", 1)[1] + "/" + notice: all_sources[path.rsplit("/", 1)[1]][notice]
               for path, definition in component["sources"].items() for notice in definition["notices"]}
    if args.operation == "build":
        if json.loads(os.environ["SYNCWATCH_DEPENDENCY_FLAGS"]) != {"profile": profile["profile"]}:
            raise ValueError("Unknown concurrency source profile")
        payload = Path(os.environ["SYNCWATCH_DEPENDENCY_OUTPUT"])
        runtime = payload / "runtime"
        runtime.mkdir()
        environment = dict(os.environ, SYNCWATCH_DEPENDENCY_OUTPUT=str(runtime),
                           SYNCWATCH_DEPENDENCY_FLAGS=json.dumps({"profile": stdlib_profile["profile"], "version": stdlib_profile["version"]}))
        subprocess.run([sys.executable, str(ROOT / "tools/jvm/stdlib.py"), "build"], env=environment, check=True)
        assemble(files, profile, payload, home, compiler)
        (payload / "concurrency-sources.jar").write_bytes(jar_bytes(support(files, profile)))
        for name, data in notices.items():
            path = payload / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    else:
        payload = directory / "payload"
    verify(payload, files, profile, notices)
    stdlib.verify(payload / "runtime", runtime_sources, source_profile, stdlib_profile, annotation_files, annotation_profile, sdk["version"])
    if args.operation == "verify":
        probe(payload, home, compiler)


if __name__ == "__main__":
    main()
