"""Offline Kotlin stdlib JVM build from the reviewed Git source exports."""

import argparse
import io
import json
import os
from pathlib import Path
import tempfile
import zipfile

import annotations
import jdk
import kotlin
import stdlib_sources
from build_support import digest, encoded, jar_bytes, run, tools


ROOT = Path(__file__).resolve().parents[2]
COMPONENT = "kotlin-stdlib"
BINARY = "kotlin-stdlib-2.3.20-syncwatch.jar"
VERSION_SOURCE = "libraries/stdlib/src/kotlin/util/KotlinVersion.kt"


def profile_data():
    profile = json.loads((ROOT / "tools/jvm/stdlib.json").read_text())
    sources = stdlib_sources.profile_data()
    registered = json.loads((ROOT / "tools/dependencies/components.json").read_text())["components"][COMPONENT]
    expected = json.loads((ROOT / "tools/dependencies/components.json").read_text())["components"]
    if (registered["sources"] != expected["kotlin-stdlib-sources"]["sources"] | expected["jvm-annotations"]["sources"]
            or registered["roots"] != ["3rdparty/kotlin-stdlib", "3rdparty/jvm-annotations"]
            or profile["version"] != sources["version"] or profile["version"] != kotlin.specification()["version"]):
        raise ValueError("Stdlib binary source/compiler graph differs from its registered profile")
    return profile, sources


def derivative(original):
    before = b"KotlinVersion(2, 3, 255)"
    if original.count(before) != 1:
        raise ValueError("KotlinVersion source no longer matches the reviewed version substitution")
    return original.replace(before, b"KotlinVersion(2, 3, 20)")


def metadata(profile):
    return {k: v for k, v in profile.items() if k != "expectedJars"} | {
        "compilerSdkInventorySha256": digest((ROOT / "tools/jvm/kotlin_toolchain.json").read_bytes()),
        "jdk": json.loads((ROOT / "tools/jvm/toolchains.json").read_text())["version"],
        "sourceSelectionSha256": digest((ROOT / "tools/jvm/stdlib_sources.json").read_bytes()),
        "modifications": {VERSION_SOURCE: "Build copy: replace KotlinVersion(2, 3, 255) with KotlinVersion(2, 3, 20). Original retained unchanged."}}


def javac(arguments, work, home):
    path = work / "javac-arguments.txt"
    kotlin.argument_file(arguments, path)
    return run([tools(home)["javac"], "@" + path.name], work)


def assemble(originals, source_profile, profile, annotation_jar, home, compiler):
    with tempfile.TemporaryDirectory(prefix="stdlib-compile-") as temporary:
        work = Path(temporary)
        names = source_profile["roles"]["common"] + source_profile["roles"]["jvm"] + source_profile["roles"]["module"]
        for name in names:
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(derivative(originals[name]) if name == VERSION_SOURCE else originals[name])
        classes, module, empty = (work / n for n in ("classes", "module", "empty"))
        for directory in (classes, module, empty):
            directory.mkdir()
        common = [str(work / n) for n in source_profile["roles"]["common"]]
        if any("," in n for n in common):
            raise ValueError("Kotlin common source arguments cannot contain commas")
        arguments = ["-no-stdlib", "-no-reflect", "-jdk-home", str(home), "-classpath", str(annotation_jar),
                     *profile["compilerArguments"], "-Xcommon-sources=" + ",".join(common), "-d", str(classes),
                     *[str(work / n) for n in names if n not in source_profile["roles"]["module"]]]
        kotlin.compile(arguments, work, home, compiler)
        flags = ["-g:none", "-encoding", "UTF-8", "-proc:none", "--source-path", str(empty), "--processor-path", str(empty)]
        javac(["--release", "8", *flags, "--class-path", os.pathsep.join([str(classes), str(annotation_jar)]),
               "-d", str(classes), *[str(work / n) for n in source_profile["roles"]["jvm"] if n.endswith(".java")]], work, home)
        module_flags = flags.copy()
        module_flags[module_flags.index("--source-path") + 1] = str((work / source_profile["roles"]["module"][0]).parent)
        javac(["--release", "9", *module_flags, "--class-path", str(empty), "--patch-module", "kotlin.stdlib=" + str(classes),
               "-d", str(module), str(work / source_profile["roles"]["module"][0])], work, home)
        entries = {p.relative_to(classes).as_posix(): p.read_bytes() for p in classes.rglob("*") if p.is_file()}
        if any(not n.endswith((".class", ".kotlin_module", ".kotlin_builtins")) for n in entries):
            raise ValueError("Unexpected Kotlin compiler output")
        entries["META-INF/versions/9/module-info.class"] = (module / "module-info.class").read_bytes()
        entries["META-INF/MANIFEST.MF"] = ("Manifest-Version: 1.0\r\nMulti-Release: true\r\n"
                                           "Implementation-Version: 2.3.20-syncwatch\r\n\r\n").encode()
        return entries


def support(files, source_profile, profile):
    original = stdlib_sources.payload_files(files, source_profile)
    original["binary-profile.json"] = encoded(metadata(profile))
    original["derivatives/" + VERSION_SOURCE] = derivative(files["kotlin-stdlib"][VERSION_SOURCE])
    original["CHANGES.txt"] = ("SyncWatch Kotlin stdlib 2.3.20 JVM profile\n"
        "The common, JVM, JDK7 and JDK8 declarations are compiled together into one metadata module.\n"
        "This is a modified build profile, not the upstream Gradle artifact or a binary-equivalence claim.\n"
        "The original KotlinVersion source and notices are in the source archive. Its build copy changes\n"
        "the upstream 2.3.255 placeholder to 2.3.20. No other selected source bytes are modified.\n"
        "The original JPMS descriptor is compiled for Java 9; Java/Kotlin classes target Java 8.\n").encode()
    return original


def verify(payload, files, source_profile, profile, annotation_files, annotation_profile, jdk_version):
    expected = support(files, source_profile, profile)
    expected |= {"annotations/" + n: data for n, data in annotations.support_files(annotation_files, annotation_profile, jdk_version).items()}
    expected |= {"notices/jvm-annotations/" + n: annotation_files[n] for n in annotation_profile["notices"]}
    annotation_names = {"annotations/" + n for n in (annotations.BINARY, annotations.SOURCES)}
    actual = set()
    for path in payload.rglob("*"):
        if path.is_symlink():
            raise ValueError("Stdlib payload contains a symbolic link")
        if path.is_file():
            name = path.relative_to(payload).as_posix()
            actual.add(name)
            if name in expected and path.read_bytes() != expected[name]:
                raise ValueError("Stdlib source/notice/profile correspondence changed: " + name)
    if actual != set(expected) | annotation_names | {BINARY}:
        raise ValueError("Stdlib payload has missing or unexpected files")
    annotations.verify(payload / "annotations", annotation_files, annotation_profile, jdk_version)
    binary = (payload / BINARY).read_bytes()
    if digest(binary) != profile["expectedJars"][jdk.current_target()][BINARY]:
        raise ValueError("Stdlib binary differs from the reviewed source/compiler output")
    with zipfile.ZipFile(io.BytesIO(binary)) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("Stdlib binary has duplicate entries")
        for name in ("THIRD-PARTY-NOTICES.txt", "source-inventory.json", "unicode-provenance.json", "binary-profile.json", "CHANGES.txt"):
            if archive.read("META-INF/" + name) != expected[name]:
                raise ValueError("Stdlib binary notices/source metadata changed")


def probe(payload, home, compiler):
    with tempfile.TemporaryDirectory(prefix="stdlib-consumer-") as temporary:
        work = Path(temporary) / "Кино 映画"
        work.mkdir()
        binary = (payload / BINARY).resolve()
        annotation_jar = (payload / "annotations" / annotations.BINARY).resolve()
        classes = work / "compiled classes"
        classes.mkdir()
        consumer = work / "StdlibConsumer.kt"
        consumer.write_bytes((ROOT / "tools/jvm/tests/StdlibConsumer.kt").read_bytes())
        kotlin.compile(["-no-stdlib", "-no-reflect", "-jdk-home", str(home), "-classpath", str(binary),
                        "-jvm-target", "1.8", "-language-version", "2.3", "-api-version", "2.3", "-Werror",
                        "-d", str(classes), str(consumer)], work, home, compiler)
        result = kotlin.java(["-cp", os.pathsep.join(map(str, [classes, binary, annotation_jar])), "StdlibConsumerKt", str(binary)], work, home)
        if "SYNCWATCH_STDLIB_OK" not in result:
            raise ValueError("Kotlin source-built runtime consumer failed")
        javac(["--release", "9", "-encoding", "UTF-8", "-proc:none", "--class-path", str(binary), "-d", str(classes),
               str(ROOT / "tools/jvm/tests/StdlibModuleProbe.java")], work, home)
        result += kotlin.java(["--module-path", str(binary), "--add-modules", "kotlin.stdlib", "-cp", str(classes),
                               "StdlibModuleProbe", str(binary)], work, home)
        dependencies = run([tools(home)["jdeps"], "--multi-release", "9", "--class-path", str(annotation_jar),
                            "--print-module-deps", str(binary)], work).strip()
        if dependencies != "java.base":
            raise ValueError("Stdlib has an undeclared runtime dependency: " + dependencies)
        print(result.strip() + "; SDK-only java.base dependency")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "verify"))
    parser.add_argument("--platform", choices=("linux-x64", "macos-arm64", "windows-x64"))
    args = parser.parse_args()
    profile, source_profile = profile_data()
    annotation_profile, sdk = annotations.profile_data()
    home, compiler = jdk.home(), kotlin.home()
    if args.operation == "build":
        if json.loads(os.environ["SYNCWATCH_DEPENDENCY_FLAGS"]) != {"profile": profile["profile"], "version": profile["version"]}:
            raise ValueError("Unknown stdlib binary profile")
        directory = Path(os.environ["SYNCWATCH_DEPENDENCY_SOURCES"])
        files = {name: stdlib_sources.source_files(directory / spec["path"], spec) for name, spec in source_profile["sources"].items()}
        annotation_files = annotations.source_files(directory / annotation_profile["sourcePath"], annotation_profile)
        payload = Path(os.environ["SYNCWATCH_DEPENDENCY_OUTPUT"])
        expected = support(files, source_profile, profile)
        expected |= {"annotations/" + n: data for n, data in (
            annotations.assemble(annotation_files, annotation_profile, home, sdk["version"])
            | annotations.support_files(annotation_files, annotation_profile, sdk["version"])).items()}
        expected |= {"notices/jvm-annotations/" + n: annotation_files[n] for n in annotation_profile["notices"]}
        for name, data in expected.items():
            path = payload / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        entries = assemble(files["kotlin-stdlib"], source_profile, profile, payload / "annotations" / annotations.BINARY, home, compiler)
        entries |= {"META-INF/" + n: expected[n] for n in ("THIRD-PARTY-NOTICES.txt", "source-inventory.json", "unicode-provenance.json", "binary-profile.json", "CHANGES.txt")}
        (payload / BINARY).write_bytes(jar_bytes(entries))
    else:
        directory = ROOT / "artifacts/dependencies" / COMPONENT / (args.platform or jdk.current_target())
        files = {name: stdlib_sources.source_files(directory / (name + ".tar"), spec) for name, spec in source_profile["sources"].items()}
        annotation_files = annotations.source_files(directory / "jvm-annotations.tar", annotation_profile)
        payload = directory / "payload"
    verify(payload, files, source_profile, profile, annotation_files, annotation_profile, sdk["version"])
    if args.operation == "verify":
        probe(payload, home, compiler)
    print("Verified source-built Kotlin stdlib, original notices, modified build profile and Java 9 module")


if __name__ == "__main__":
    main()
