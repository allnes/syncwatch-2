"""Build and verify the source-only Java Annotations JVM profile."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile

import jdk


ROOT = Path(__file__).resolve().parents[2]
BINARY = "annotations-26.0.2-syncwatch.jar"
SOURCES = "annotations-26.0.2-syncwatch-sources.jar"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_files(source, profile):
    wanted = set(profile["sources"]) | set(profile["notices"])
    if source.is_dir():
        java = {p.relative_to(source).as_posix() for p in (source / "src/jvmMain").rglob("*.java")}
        files = {name: (source / name).read_bytes() for name in wanted}
    else:
        with tarfile.open(source) as archive:
            if archive.pax_headers.get("comment") != profile["revision"]:
                raise ValueError("Annotations source archive has a different Git revision")
            java = {m.name for m in archive if m.isfile() and m.name.startswith("src/jvmMain/") and m.name.endswith(".java")}
            files = {name: archive.extractfile(name).read() for name in wanted}
    if java != set(profile["sources"]):
        raise ValueError("Java source selection differs from the reviewed inventory")
    for name, expected in (profile["sources"] | profile["notices"]).items():
        if digest(files[name]) != expected:
            raise ValueError("Source or notice digest changed: " + name)
    exceptions = set(profile["repositoryLicensedFiles"])
    actual = set()
    for name in profile["sources"]:
        data = files[name]
        if not data.startswith(b"/*"):
            actual.add(name)
        elif b"Licensed under the Apache License, Version 2.0" not in data.split(b"*/", 1)[0]:
            raise ValueError("Unreviewed Java source license: " + name)
    if actual != exceptions or b"License-Apache%202.0" not in files["README.md"]:
        raise ValueError("Repository-wide Apache declaration does not match the reviewed source scope")
    if b"projectVersion=26.0.2" not in files["gradle.properties"]:
        raise ValueError("Upstream source version differs from the profile")
    return files


def notices(files, profile):
    headers = sorted({files[n].split(b"*/", 1)[0] + b"*/" for n in profile["sources"] if files[n].startswith(b"/*")})
    return (b"JetBrains Java Annotations 26.0.2\n"
            b"Upstream: https://github.com/JetBrains/java-annotations\n"
            + b"Source revision: " + profile["revision"].encode() + b"\n\n"
            + files["LICENSE.txt"] + b"\n\nOriginal source notices:\n\n" + b"\n\n".join(headers)
            + b"\n\nFiles covered by the repository-wide Apache declaration (no original file header):\n"
            + b"\n".join(n.encode() for n in sorted(profile["repositoryLicensedFiles"]))
            + b"\n\nThe unmodified upstream README and selected Java sources accompany this artifact.\n")


def metadata(profile, version):
    return {k: profile[k] for k in ("schemaVersion", "coordinate", "sourcePath", "revision", "license", "javaRelease",
                                   "moduleRelease", "sources", "notices", "repositoryLicensedFiles")} | {"compiler": "Temurin JDK " + version}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def jar_bytes(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return stream.getvalue()


def tools(home):
    suffix = ".exe" if os.name == "nt" else ""
    return {n: str(home / "bin" / (n + suffix)) for n in ("java", "javac", "jdeps")}


def run(arguments, directory):
    environment = {k: v for k, v in os.environ.items() if k not in {"JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS", "CLASSPATH"}}
    try:
        return subprocess.check_output(arguments, cwd=directory, env=environment, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as error:
        print(error.output, file=sys.stderr)
        raise


def assemble(files, profile, home, version):
    commands = tools(home)
    with tempfile.TemporaryDirectory(prefix="annotations-compile-") as temporary:
        work = Path(temporary)
        for name in profile["sources"]:
            path = work / name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(files[name])
        classes, module, empty = (work / n for n in ("classes", "module", "empty"))
        for path in (classes, module, empty):path.mkdir()
        flags = ["-g:none", "-encoding", "UTF-8", "-proc:none", "-Xlint:all,-options", "-Werror",
                 "--class-path", str(empty), "--source-path", str(empty), "--processor-path", str(empty)]
        java = [str(work / n) for n in sorted(profile["sources"]) if "/java/" in n]
        run([commands["javac"], "--release", str(profile["javaRelease"]), *flags, "-d", str(classes), *java], work)
        module_flags = flags.copy()
        module_flags[module_flags.index("--source-path") + 1] = str(work / "src/jvmMain/moduleInfo")
        run([commands["javac"], "--release", str(profile["moduleRelease"]), *module_flags, "--patch-module",
             "org.jetbrains.annotations=" + str(classes), "-d", str(module),
             str(work / "src/jvmMain/moduleInfo/module-info.java")], work)
        entries = {p.relative_to(classes).as_posix(): p.read_bytes() for p in classes.rglob("*.class")}
        entries["META-INF/versions/9/module-info.class"] = (module / "module-info.class").read_bytes()
        entries["META-INF/MANIFEST.MF"] = b"Manifest-Version: 1.0\r\nMulti-Release: true\r\nImplementation-Version: 26.0.2\r\n\r\n"
        common = {"META-INF/LICENSE.txt": files["LICENSE.txt"], "META-INF/UPSTREAM-README.md": files["README.md"],
                  "META-INF/THIRD-PARTY-NOTICES.txt": notices(files, profile), "META-INF/source-inventory.json": encoded(metadata(profile, version))}
        return {BINARY: jar_bytes(entries | common), SOURCES: jar_bytes({n: files[n] for n in profile["sources"]} | common)}


def support_files(files, profile, version):
    return {"THIRD-PARTY-NOTICES.txt": notices(files, profile), "source-inventory.json": encoded(metadata(profile, version)),
            "notices/jvm-annotations/LICENSE.txt": files["LICENSE.txt"], "notices/jvm-annotations/README.md": files["README.md"]}


def verify(payload, files, profile, version):
    expected = support_files(files, profile, version)
    actual = {p.relative_to(payload).as_posix() for p in payload.rglob("*") if p.is_file()}
    if actual != set(expected) | {BINARY, SOURCES}:
        raise ValueError("Annotations artifact has missing or unexpected files")
    for name, data in expected.items():
        if (payload / name).read_bytes() != data:
            raise ValueError("Annotations notices/source inventory changed: " + name)
    for name in (BINARY, SOURCES):
        data = (payload / name).read_bytes()
        if digest(data) != profile["expectedJars"][name]:
            raise ValueError("Annotations JAR differs from the reviewed source/compiler output: " + name)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member, content in {"META-INF/LICENSE.txt": files["LICENSE.txt"], "META-INF/THIRD-PARTY-NOTICES.txt": notices(files, profile),
                                    "META-INF/UPSTREAM-README.md": files["README.md"], "META-INF/source-inventory.json": encoded(metadata(profile, version))}.items():
                if archive.read(member) != content:
                    raise ValueError("Annotations JAR is missing complete notices or source correspondence")
    with zipfile.ZipFile(payload / SOURCES) as archive:
        for name in profile["sources"]:
            if archive.read(name) != files[name]:raise ValueError("Annotations source JAR changed upstream source bytes")


def probe(payload, home):
    commands = tools(home)
    with tempfile.TemporaryDirectory(prefix="annotations-probe-") as temporary:
        work = Path(temporary)
        binary = str((payload / BINARY).resolve())
        run([commands["javac"], "--release", "8", "-proc:none", "-classpath", binary, "-d", str(work),
             str(ROOT / "tools/jvm/tests/AnnotationsConsumer.java")], work)
        run([commands["javac"], "--release", "9", "-proc:none", "-classpath", binary, "-d", str(work),
             str(ROOT / "tools/jvm/tests/AnnotationsProbe.java")], work)
        result = run([commands["java"], "-cp", os.pathsep.join([str(work), binary]), "AnnotationsProbe", binary], work)
        negative = work / "InvalidTarget.java"
        negative.write_text('class InvalidTarget { @org.jetbrains.annotations.Contract("-> null") int field; }\n')
        p = subprocess.run([commands["javac"], "--release", "8", "-proc:none", "-XDrawDiagnostics", "-classpath", binary,
                            "-d", str(work), str(negative)], cwd=work, text=True, capture_output=True)
        if p.returncode == 0 or "compiler.err.annotation.type.not.applicable" not in p.stderr:
            raise ValueError("Annotations invalid-target consumer was not rejected")
        dependencies = run([commands["jdeps"], "--multi-release", "9", "--print-module-deps", binary], work).strip()
        modules = set(dependencies.split(","))
        if "java.base" not in modules or not modules <= {"java.base", "java.desktop"}:
            raise ValueError("Annotations has an undeclared non-SDK module dependency")
        print(result.strip() + "; invalid-target consumer rejected; SDK-only module graph")


def profile_data():
    profile = json.loads((ROOT / "tools/jvm/annotations.json").read_text())
    registered = json.loads((ROOT / "tools/dependencies/components.json").read_text())["components"]["jvm-annotations"]
    source = registered["sources"][profile["sourcePath"]]
    if source["revision"] != profile["revision"] or source["license"] != profile["license"] or source["requires"]:
        raise ValueError("Annotations source/license profile differs from the registered graph")
    return profile, json.loads((ROOT / "tools/jvm/toolchains.json").read_text())


def build(source, payload):
    profile, sdk = profile_data()
    files = source_files(source, profile);home = jdk.home()
    for name, data in (assemble(files, profile, home, sdk["version"]) | support_files(files, profile, sdk["version"])).items():
        path = payload / name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(data)
    verify(payload, files, profile, sdk["version"])
    probe(payload, home)
    print("Built Annotations 26.0.2 from 32 unchanged source files; complete Apache notices retained")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "verify"))
    parser.add_argument("--platform", choices=("linux-x64", "macos-arm64", "windows-x64"))
    args = parser.parse_args()
    if args.operation == "build":
        flags = json.loads(os.environ["SYNCWATCH_DEPENDENCY_FLAGS"])
        if flags != {"profile": "java8-module9-v1", "version": "26.0.2"}:raise ValueError("Unknown annotations build profile")
        build(Path(os.environ["SYNCWATCH_DEPENDENCY_SOURCES"]) / "3rdparty/jvm-annotations", Path(os.environ["SYNCWATCH_DEPENDENCY_OUTPUT"]))
    else:
        target = args.platform or jdk.current_target()
        directory = ROOT / "artifacts/dependencies/jvm-annotations" / target
        profile, sdk = profile_data();files = source_files(directory / "jvm-annotations.tar", profile)
        verify(directory / "payload", files, profile, sdk["version"])
        probe(directory / "payload", jdk.home())
        print("Verified Annotations source correspondence and notices, including restored caches")


if __name__ == "__main__":
    main()
