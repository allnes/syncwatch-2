"""Exact original CPython SipHash fragments and generic native transcript orchestration."""

import hashlib
from pathlib import Path
import re
import sys

from siphash_oracle import corpus_header

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/native"))
sys.path.insert(0, str(ROOT / "tools/compression"))
from c_probe import compile_transcript
from toolchain import resolve


def fragments(cpython):
    def unique(pattern, data):
        matches = re.findall(pattern, data, re.S)
        if len(matches) != 1:
            raise ValueError("Missing or ambiguous original SipHash fragment")
        return matches[0]
    result = {
        "attribution": unique(rb"(/\* \*+\n <MIT License>.*?\*/)", cpython["Python/pyhash.c"]),
        "pointerType": unique(rb"(typedef intptr_t +Py_intptr_t;)", cpython["Include/pyport.h"]),
        "algorithmConstants": unique(rb"(#define Py_HASH_EXTERNAL 0\n#define Py_HASH_SIPHASH24 1\n#define Py_HASH_FNV 2\n#define Py_HASH_SIPHASH13 3)", cpython["Include/pyhash.h"]),
        "sizeType": unique(rb"(typedef Py_intptr_t +Py_ssize_t;)", cpython["Include/pyport.h"]),
        "algorithms": unique(rb"(/\* byte swap little endian to host endian.*?\nuint64_t\n_Py_KeyedHash\(.*?\n\})", cpython["Python/pyhash.c"]),
    }
    return result


def fixture(cpython):
    pieces = fragments(cpython)
    content = (b"/* Exact original CPython fragments; full original MIT/PSF notices accompany sources. */\n"
               + pieces["attribution"] + b"\n" + pieces["pointerType"] + b"\n" + pieces["sizeType"] + b"\n" + pieces["algorithmConstants"] + b"\n"
               + b"/* Explicit first-party probe configuration; both original variants are compiled. */\n"
               + b"#define PY_LITTLE_ENDIAN 1\n#define Py_HASH_ALGORITHM Py_HASH_SIPHASH24\n"
               + pieces["algorithms"] + b"\n")
    return content, {name: hashlib.sha256(data).hexdigest() for name, data in pieces.items()}


def native_proof(sources, expected, cmake, options, sdk):
    content, hashes = fixture(sources["cpython"])
    corpus = corpus_header(sources)
    compile_transcript(ROOT / "tools/python-siphash/native", {"fixture.h": content, "corpus.h": corpus, "NOTICES.txt": sources["cpython"]["LICENSE"]}, expected, cmake, options)
    return {"sdk": sdk, "transcript": expected, "originalFragmentSha256": hashes,
            "corpusSha256": hashlib.sha256(corpus).hexdigest(), "pythonSdkLinked": False,
            "configuration": {"littleEndian": True, "sizeBits": 64, "compileSipHash24": True}}
