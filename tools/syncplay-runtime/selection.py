"""Record and check the exact original inputs for the headless runtime build."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess

from source_graph import ROOT, graph_data


def original_files(repository, revision):
    entries = {}
    for row in subprocess.check_output(["git", "ls-tree", "-r", "-z", revision], cwd=repository).split(b"\0"):
        if row:
            metadata, name = row.decode().split("\t")
            mode, kind, oid = metadata.split()
            entries[name] = mode, oid
    return entries


def raw_blobs(repository, identities):
    identities = list(dict.fromkeys(identities))
    raw = subprocess.check_output(["git", "cat-file", "--batch"], cwd=repository,
                                  input=("\n".join(identities) + "\n").encode())
    stream = io.BytesIO(raw)
    result = {}
    for oid in identities:
        header = stream.readline().split()
        if header[:2] != [oid.encode(), b"blob"]:
            raise ValueError("Unexpected source object")
        result[oid] = stream.read(int(header[2]))
        if stream.read(1) != b"\n":
            raise ValueError("Truncated original source object")
    return result


def exports(entries, selected, prefix=""):
    available = {n for n in entries if n.startswith(prefix)}
    wanted = available & selected
    if not wanted:
        return []
    if prefix and wanted == available:
        return [prefix.rstrip("/")]
    result = []
    for part in sorted({n[len(prefix):].split("/")[0] for n in wanted}):
        name = prefix + part
        result += [name] if name in entries else exports(entries, selected, name + "/")
    return result


def select(name, entry, entries, graph):
    notices = set(entry["noticeSha256"])
    if name == "idna-unicode-data":
        ucd = "unicodetools/data/ucd/18.0.0/"
        idna = "unicodetools/data/idna/18.0.0/"
        return notices | {ucd + name for name in ["ReadMe.txt", "UnicodeData.txt", "PropList.txt",
            "DerivedCoreProperties.txt", "Blocks.txt", "HangulSyllableType.txt",
            "extracted/DerivedJoiningType.txt", "Scripts.txt", "DerivedNormalizationProps.txt"]} | {
            idna + "IdnaMappingTable.txt", idna + "IdnaTestV2.txt"}
    if name == "license-texts":
        return notices | {"text/CC0-1.0.txt"}
    if name == "boringssl":
        return notices | {"crypto/pkcs8/pkcs8.cc"}
    excluded = {"test", "tests", "testsuite", "test-data", "vectors", "fuzz", "fuzzing", "benches", "benchmarks", "examples", "doc", "docs", "demos"}
    selected = {n for n in entries if not n.startswith(".") and not any(p in excluded for p in n.split("/")[:-1])
                and not n.endswith((".obj", ".o", ".lib", ".dll", ".pyd", ".so", ".a", ".png", ".jpg", ".svg", ".pdf"))
                and entries[n][0] in {"100644", "100755"}}
    # Rust documentation is sometimes a compiler input via include_str!.
    if name == "openssl":
        # Configure reads the directory graph even for disabled test/fuzz/docs
        # targets. Retain their original build declarations, not their code.
        selected |= {n for n in entries if n.endswith("/build.info")}
    if name == "rust-pyo3":
        selected |= {n for n in entries if n.startswith("guide/") and n.endswith(".md")}
    if name == "libffi":
        selected |= {"doc/Makefile.am", "testsuite/Makefile.am"}
        selected = {n for n in selected if not n.startswith("src/") or "/" not in n.removeprefix("src/")
                    or n.startswith(("src/aarch64/", "src/x86/")) or n.endswith(".h")}
    return selected | notices


def record():
    graph = graph_data()
    specifications = {}
    for name, source in graph["sources"].items():
        repository = ROOT / source["path"]
        entries = original_files(repository, source["revision"])
        selected = select(name, source, entries, graph)
        if not selected <= set(entries):
            raise ValueError("Selected original is missing: " + name)
        if any(entries[n][0] not in {"100644", "100755"} for n in selected):
            raise ValueError("Runtime source selection requires original regular files")
        data = raw_blobs(repository, [entries[n][1] for n in sorted(selected)])
        roots = sorted(exports(entries, selected))
        if not 0 < len(roots) <= 512:
            raise ValueError("Source selection exceeds the bounded export contract: " + name)
        files = {n: hashlib.sha256(data[entries[n][1]]).hexdigest() for n in sorted(selected)}
        if any(files[n] != expected for n, expected in source["noticeSha256"].items()):
            raise ValueError("Original source notice differs")
        specifications[name] = {"path": source["path"], "revision": source["revision"], "license": source["license"],
                               "exports": roots, "notices": sorted(source["noticeSha256"]), "files": files,
                               "executables": sorted(n for n in selected if entries[n][0] == "100755")}
    return {"schemaVersion": 1, "profile": graph["profile"], "sources": specifications}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    data = json.dumps(record(), indent=2) + "\n"
    path = Path(__file__).with_name("sources.json")
    if args.record:
        path.write_text(data, encoding="utf-8")
    elif path.read_text(encoding="utf-8") != data:
        raise ValueError("Runtime source inventory differs from pinned originals")
    print("Exact runtime source inventory " + ("recorded" if args.record else "verified"))
