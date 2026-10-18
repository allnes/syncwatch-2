"""Package reviewed Kotlin stdlib sources and verify Unicode provenance offline."""

# Titlecase logic adapted from JetBrains/kotlin's Unicode builders/writer and generated source.
# Copyright 2010-2021 JetBrains s.r.o. and Kotlin Programming Language contributors.
# Copyright 2010-2023 JetBrains s.r.o. and Kotlin Programming Language contributors.
# Use of this source code is governed by the Apache 2.0 license (see LICENSE).
# SyncWatch changes: Python offline evaluation, exact source/data checks and archive verification.

import argparse
import json
import os
from pathlib import Path
import platform
import tarfile

from build_support import digest, encoded, jar_bytes


ROOT = Path(__file__).resolve().parents[2]
COMPONENT = "kotlin-stdlib-sources"
GENERATED = "libraries/stdlib/common/src/generated/_OneToManyTitlecaseMappings.kt"
GENERATOR = "libraries/tools/kotlin-stdlib-gen/src/generators/unicode/GenerateUnicodeData.kt"


def profile_data():
    profile = json.loads((ROOT / "tools/jvm/stdlib_sources.json").read_text())
    component = json.loads((ROOT / "tools/dependencies/components.json").read_text())["components"][COMPONENT]
    if profile["schemaVersion"] != 1 or profile["binaryReady"] is not False:
        raise ValueError("Only the reviewed source-only profile is supported")
    expected = {}
    for name, source in profile["sources"].items():
        expected[source["path"]] = {k: source[k] for k in ("revision", "license", "notices", "exports")} | {
            "requires": ["3rdparty/unicode-data"] if name == "kotlin-stdlib" else [], "unusedSubmodules": {}}
    if component["sources"] != expected or component["roots"] != ["3rdparty/kotlin-stdlib"]:
        raise ValueError("Stdlib source/license profile differs from the registered graph")
    return profile


def source_files(path, specification):
    if path.is_dir():
        files = {}
        for p in path.rglob("*"):
            if p.is_symlink():
                raise ValueError("Source snapshot must contain only regular files")
            if p.is_file():
                files[p.relative_to(path).as_posix()] = p.read_bytes()
    else:
        files = {}
        with tarfile.open(path) as archive:
            if archive.pax_headers.get("comment") != specification["revision"]:
                raise ValueError("Source archive has a different Git revision")
            for item in archive:
                if item.isdir():
                    continue
                if not item.isfile() or item.name in files:
                    raise ValueError("Source snapshot must contain unique regular files")
                files[item.name] = archive.extractfile(item).read()
    if set(files) != set(specification["files"]):
        raise ValueError("Source snapshot differs from the reviewed file inventory")
    for name, data in files.items():
        if digest(data) != specification["files"][name]:
            raise ValueError("Source or notice digest changed: " + name)
    return files


def apache_header(data):
    data = data.lstrip()
    if not data.startswith(b"/*"):
        return None
    header, separator, _tail = data.partition(b"*/")
    if separator and any(term in header for term in (b"Apache 2.0 license", b"Licensed under the Apache License, Version 2.0")):
        return header + separator
    return None


def check_licenses(files, profile):
    code = {n for n in files if n.endswith((".kt", ".java"))}
    roles = [n for names in profile["roles"].values() for n in names]
    if len(roles) != len(set(roles)) or set(roles) != code:
        raise ValueError("Source roles do not cover the exact selected code")
    unheaded = {n for n in code if apache_header(files[n]) is None}
    if unheaded != set(profile["repositoryLicensedFiles"]):
        raise ValueError("Source Apache headers differ from the reviewed exceptions")
    if b"applies to all code in this repository which is copyright" not in files["license/README.md"]:
        raise ValueError("Missing repository-wide license declaration")


def titlecase_mappings(unicode_data, special_casing):
    """Follow the pinned builder using Unicode 13 data, never host Unicode tables."""
    records = {}
    for line in unicode_data.decode("utf-8").splitlines():
        fields = line.split(";")
        if len(fields) != 15:
            raise ValueError("Invalid UnicodeData record")
        point = int(fields[0], 16)
        if point in records:
            raise ValueError("Duplicate UnicodeData code point")
        records[point] = fields
    mappings = {}
    seen = set()
    for raw in special_casing.decode("utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = [p.strip() for p in line.split(";")]
        if len(fields) not in (5, 6):
            raise ValueError("Invalid SpecialCasing record")
        if fields[4]:
            continue
        point = int(fields[0], 16)
        if point > 0xffff or point in seen:
            raise ValueError("Unreviewed unconditional special casing")
        seen.add(point)
        title = [int(p, 16) for p in fields[2].split()]
        upper = [int(p, 16) for p in fields[3].split()]
        if not title or not upper or any(p > 0xffff for p in title + upper):
            raise ValueError("Unsupported titlecase mapping")
        lower_tail = [int(records[p][13], 16) if p in records and records[p][13] else p for p in upper[1:]]
        if title == [upper[0], *lower_tail]:
            continue
        if len(title) == 1:
            simple = records.get(point)
            if title != [int(simple[14], 16) if simple and simple[14] else point]:
                raise ValueError("Simple and special titlecase mappings disagree")
            continue
        mappings[f"{point:04X}"] = [f"{p:04X}" for p in title]
    return dict(sorted(mappings.items()))


def unicode_report(kotlin, unicode, profile):
    publication = profile["unicodePublication"]
    inputs = publication["files"]
    for name, item in inputs.items():
        if digest(unicode[item["source"]]) != item["sha256"]:
            raise ValueError("Unicode data differ from the reviewed published release: " + name)
    version = publication["version"]
    if ('private const val unicodeVersion = "' + version + '"').encode() not in kotlin[GENERATOR]:
        raise ValueError("Kotlin Unicode generator version changed")
    if ("# SpecialCasing-" + version + ".txt").encode() not in unicode[inputs["SpecialCasing.txt"]["source"]]:
        raise ValueError("SpecialCasing version changed")
    mappings = titlecase_mappings(unicode[inputs["UnicodeData.txt"]["source"]], unicode[inputs["SpecialCasing.txt"]["source"]])
    if mappings != profile["titlecaseMappings"]:
        raise ValueError("Generated titlecase mappings differ from the reviewed inventory")
    non_greek = {n: v for n, v in mappings.items() if not 0x1f00 <= int(n, 16) <= 0x1fff}
    if non_greek != {"0149": ["02BC", "004E"]}:
        raise ValueError("Upstream titlecase writer assumptions no longer hold")
    body = r"""internal fun Char.titlecaseImpl(): String {
    val uppercase = uppercase()
    if (uppercase.length > 1) {
        return if (this == '\u0149') uppercase else uppercase[0] + uppercase.substring(1).lowercase()
    }
    return titlecaseChar().toString()
}
"""
    expected = (f"// {len(mappings)} mappings totally\n" + body).encode()
    if kotlin[GENERATED].split(b"// 10 mappings totally\n", 1)[-1] != body.encode() or not kotlin[GENERATED].endswith(expected):
        raise ValueError("Committed Kotlin titlecase function differs from its data-derived writer")
    return {"schemaVersion": 1, "unicodePublication": publication, "mappings": mappings,
            "generatedSource": GENERATED, "generatedSourceSha256": digest(kotlin[GENERATED]),
            "scope": "Common/JVM titlecase generator correspondence; no runtime or other generator validation"}


def payload_files(files, profile):
    kotlin, unicode = files["kotlin-stdlib"], files["unicode-data"]
    check_licenses(kotlin, profile)
    report = unicode_report(kotlin, unicode, profile)
    notices = []
    for name, source in profile["sources"].items():
        notices.append((name + "\nSource revision: " + source["revision"] + "\nLicense: " + source["license"] + "\n").encode())
        for n in source["notices"]:
            notices.append(("\n--- " + n + " ---\n").encode() + files[name][n])
    headers = sorted({header for data in kotlin.values() if (header := apache_header(data))})
    notices.extend([b"\nOriginal Apache source headers:\n", b"\n\n".join(headers),
                    b"\n\nFiles with repository-wide licensing and no Apache block header:\n",
                    "\n".join(profile["repositoryLicensedFiles"]).encode(), b"\n"])
    # Keep the Unicode data copyright header as well as its full permission notice.
    special = unicode[profile["unicodePublication"]["files"]["SpecialCasing.txt"]["source"]]
    notices.append(b"\nOriginal SpecialCasing header:\n" + special.split(b"# Special Casing\n", 1)[0])
    common = {"source-inventory.json": encoded(profile), "unicode-provenance.json": encoded(report),
              "THIRD-PARTY-NOTICES.txt": b"\n".join(notices)}
    originals = {name + "/" + n: data for name, selected in files.items() for n, data in selected.items()}
    output = dict(common)
    output[profile["artifact"]] = jar_bytes(originals | {"META-INF/" + n: data for n, data in common.items()})
    for name, source in profile["sources"].items():
        for n in source["notices"]:
            output["notices/" + name + "/" + n] = files[name][n]
    return output


def verify(payload, expected):
    found = set()
    for path in payload.rglob("*"):
        if path.is_symlink():
            raise ValueError("Source artifact contains a symbolic link")
        if path.is_file():
            name = path.relative_to(payload).as_posix()
            found.add(name)
            if name not in expected or path.read_bytes() != expected[name]:
                raise ValueError("Source artifact or complete notices changed: " + name)
    if found != set(expected):
        raise ValueError("Source artifact has missing or unexpected files")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "verify"))
    parser.add_argument("--platform", choices=("linux-x64", "macos-arm64", "windows-x64"))
    args = parser.parse_args()
    profile = profile_data()
    if args.operation == "build":
        if json.loads(os.environ["SYNCWATCH_DEPENDENCY_FLAGS"]) != {"profile": "reviewed-sources-v1", "version": profile["version"]}:
            raise ValueError("Unknown stdlib source profile")
        files = {name: source_files(Path(os.environ["SYNCWATCH_DEPENDENCY_SOURCES"]) / s["path"], s) for name, s in profile["sources"].items()}
        payload = Path(os.environ["SYNCWATCH_DEPENDENCY_OUTPUT"])
    else:
        target = args.platform or {("Darwin", "arm64"): "macos-arm64", ("Linux", "x86_64"): "linux-x64", ("Windows", "AMD64"): "windows-x64"}[(platform.system(), platform.machine())]
        directory = ROOT / "artifacts/dependencies" / COMPONENT / target
        files = {name: source_files(directory / (name + ".tar"), s) for name, s in profile["sources"].items()}
        payload = directory / "payload"
    expected = payload_files(files, profile)
    if args.operation == "build":
        for name, data in expected.items():
            path = payload / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    verify(payload, expected)
    print("Verified Kotlin 2.3.20 source-only package, full notices and 10 Unicode 13 titlecase mappings; no binary enabled")


if __name__ == "__main__":
    main()
