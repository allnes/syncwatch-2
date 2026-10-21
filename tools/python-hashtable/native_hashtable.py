"""Extract original source without patching algorithms; own a C-only probe."""

import hashlib
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/native"))
sys.path.insert(0, str(ROOT / "tools/compression"))
from c_probe import compile_transcript
from toolchain import resolve
from hashtable_oracle import corpus_header


def fragments(cpython):
    def unique(pattern, name):
        found = re.findall(pattern, cpython[name], re.S)
        if len(found) != 1:
            raise ValueError("Missing or ambiguous original hashtable fragment")
        return found[0]
    return {
        "pointerType": unique(rb"(typedef intptr_t +Py_intptr_t;)", "Include/pyport.h"),
        "sizeType": unique(rb"(typedef Py_intptr_t +Py_ssize_t;)", "Include/pyport.h"),
        "hashType": unique(rb"(typedef Py_ssize_t Py_hash_t;)", "Include/pyport.h"),
        "unsignedHashType": unique(rb"(typedef size_t Py_uhash_t;)", "Include/pyport.h"),
        "rvalue": unique(rb"(#define _Py_RVALUE\(EXPR\) [^\n]+)", "Include/pymacro.h"),
        "pointerHash": unique(rb"(Py_hash_t\n_Py_HashPointerRaw\(const void \*p\)\n\{.*?\n\})", "Python/pyhash.c"),
        "attribution": unique(rb"(/\* The implementation of the hash table.*?\*/)", "Python/hashtable.c"),
        "implementation": unique(rb'\n#include "pycore_hashtable.h"\n\n(.*)', "Python/hashtable.c"),
        "declarations": cpython["Include/internal/pycore_hashtable.h"],
    }


def fixture(cpython):
    pieces = fragments(cpython)
    config = (b"/* First-party standalone SDK fixture ports; no Python runtime/ABI. */\n"
              b"#define Py_BUILD_CORE 1\n#define PyAPI_FUNC(TYPE) TYPE\n#define SIZEOF_VOID_P 8\n"
              b"#define PyMem_Malloc malloc\n#define PyMem_Free free\n")
    # Declarations must precede the original full implementation.
    order = ["pointerType", "sizeType", "hashType", "unsignedHashType", "rvalue",
             "declarations", "pointerHash", "attribution", "implementation"]
    content = config + b"\n".join(pieces[name] for name in order) + b"\n"
    return content, {name: hashlib.sha256(data).hexdigest() for name, data in pieces.items()}


def native_proof(sources, expected, cmake, options, sdk):
    content, hashes = fixture(sources["cpython"])
    corpus = corpus_header()
    compile_transcript(ROOT / "tools/python-hashtable/native", {"fixture.h": content, "corpus.h": corpus,
        "NOTICES.txt": sources["cpython"]["LICENSE"] + b"\n" + sources["libcfu"]["COPYING"]}, expected, cmake, options)
    return {"sdk": sdk, "transcript": expected, "originalFragmentSha256": hashes,
            "corpusSha256": hashlib.sha256(corpus).hexdigest(), "pythonSdkLinked": False,
            "configuration": {"sizeBits": 64, "assertionsEnabled": True, "allocatorPorts": "ISO C malloc/free"}}
