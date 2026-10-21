"""Exact unmodified hash source graph, embedded origins and separate namespace policy."""

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/dependencies"))
from source_files import archive_bytes, digest, encoded, read_snapshot

COMPONENT = "hacl-hash"
SUMMARY = b"SyncWatch static-hash-v1: original HACL and KaRaMeL source files are unchanged. A separate first-party namespace preinclude, verified-uint128 compiler definition and build/probe code are additions. CPython references and the cited Arduino endian origin are provenance only. No proof generator, interpreter, TLS provider, SDK runtime or executable is distributed.\n"


def profile_data():
    profile = json.loads((ROOT / "tools/hashing/profile.json").read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "tools/dependencies/components.json").read_text(encoding="utf-8"))["components"]
    expected = {}
    for source in profile["sources"].values():
        spec = {key: source[key] for key in ("revision", "license", "notices", "exports", "requires")}
        spec["unusedSubmodules"] = {}
        expected[source["path"]] = spec
    if (profile["schemaVersion"] != 1 or profile["sharedLibrary"] is not False or profile["runtimeReady"] is not False
            or profile["verifiedUint128"] is not True or profile["namespacePrefix"] != "python_hashlib_"
            or registry[COMPONENT]["sources"] != expected or registry[COMPONENT]["roots"] != ["3rdparty/cpython"]
            or registry["syncplay-runtime"]["status"] != "unavailable"):
        raise ValueError("Hash source/license profile differs from the registered static graph")
    return profile


def read_sources(paths, profile):
    return {name: read_snapshot(paths[name], source) for name, source in profile["sources"].items()}


def original_archive(sources):
    return archive_bytes({name + "/" + path: data for name, files in sources.items() for path, data in files.items()})


def macro_bodies(data, name):
    text = re.sub(rb"\\\r?\n", b"", data)
    values = re.findall(rb"^\s*#\s*define\s+" + name.encode() + rb"\(x\)([^\n]+)", text, re.M)
    return {re.sub(rb"\s+", b"", value) for value in values}


def validate_sources(sources, profile):
    if digest(original_archive(sources)) != profile["sourceArchiveSha256"]:
        raise ValueError("Original hash source archive differs")
    refresh = sources["cpython"]["Modules/_hacl/refresh.sh"]
    if b"expected_hacl_star_rev=" + profile["sources"]["hacl-star"]["revision"].encode() not in refresh:
        raise ValueError("CPython reference selects a different HACL origin")
    compiled = re.findall(rb"^\s*(Hacl_Hash_\w+\.c)\s*$", refresh, re.M)
    if [s.decode() for s in compiled] != ["Hacl_Hash_SHA2.c", "Hacl_Hash_SHA1.c", "Hacl_Hash_MD5.c", "Hacl_Hash_SHA3.c"] or set(s.decode() for s in compiled) != set(profile["compileSources"]):
        raise ValueError("CPython refresh hash selection differs")
    info = sources["hacl-star"]["dist/gcc-compatible/INFO.txt"]
    if b"Karamel version: " + profile["sources"]["karamel"]["revision"].encode() not in info:
        raise ValueError("Generated hash code identifies a different KaRaMeL origin")
    for path, expected in profile["karamelHaclCorrespondence"].items():
        data = sources["karamel"][path]
        if digest(data) != expected or data != sources["hacl-star"]["dist/karamel/" + path]:
            raise ValueError("KaRaMeL header differs from the original HACL vendor copy")
    endian = sources["karamel"]["include/krml/lowstar_endianness.h"]
    origin = sources["arduinolibs"]["libraries/Crypto/utility/EndianUtil.h"]
    if b"https://github.com/rweather/arduinolibs/" not in endian:
        raise ValueError("Endian origin citation differs")
    for name in ("htobe32", "htobe64"):
        if not macro_bodies(endian, name) & macro_bodies(origin, name):
            raise ValueError("Cited endian macro correspondence differs: " + name)


def namespace_header(sources, profile):
    code = b"\n".join(data for name, data in sources["hacl-star"].items()
                      if name.startswith("dist/gcc-compatible/") and name.endswith((".c", ".h")))
    code = re.sub(rb"/\*.*?\*/|//[^\n]*", b"", code, flags=re.S)
    macros = set(re.findall(rb"^\s*#\s*define\s+(Hacl_\w+)", code, re.M))
    names = sorted(set(re.findall(rb"\bHacl_\w+\b", code)) - macros)
    return (b"/* First-party namespace build configuration; original vendor files are unchanged. */\n"
            b"#ifndef SYNCWATCH_HACL_NAMESPACE_H\n#define SYNCWATCH_HACL_NAMESPACE_H\n" + b"".join(
                b"#define " + name + b" " + profile["namespacePrefix"].encode() + name + b"\n" for name in names) + b"#endif\n")


def public_headers(sources, profile):
    result = {"include/syncwatch_hacl_namespace.h": namespace_header(sources, profile)}
    for name, data in sources["hacl-star"].items():
        if name.startswith("dist/gcc-compatible/") and name.endswith(".h"):
            result["include/" + name.removeprefix("dist/gcc-compatible/")] = data
    for name, data in sources["karamel"].items():
        if name.endswith(".h"):
            key = name.removeprefix("include/") if name.startswith("include/") else name.removeprefix("krmllib/dist/minimal/")
            result["include/" + key] = data
    result["include/syncwatch_hacl.h"] = (b"/* SPDX-License-Identifier: Apache-2.0 */\n"
        b"#ifndef SYNCWATCH_HACL_H\n#define SYNCWATCH_HACL_H\n"
        b"#ifndef KRML_VERIFIED_UINT128\n#define KRML_VERIFIED_UINT128\n#endif\n"
        b'#include "syncwatch_hacl_namespace.h"\n' + b"".join(b'#include "Hacl_Hash_' + name + b'.h"\n' for name in [b"MD5", b"SHA1", b"SHA2", b"SHA3"]) + b"#endif\n")
    return result
