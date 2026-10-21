"""Compile original table fragments with the installed C SDK, then compare all slots."""

import hashlib
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/compression"))
from toolchain import resolve
sys.path.insert(0, str(ROOT / "tools/native"))
from c_probe import compile_transcript


def fixture(cpython, header):
    def unique(pattern, data):
        found = re.findall(pattern, data, re.S)
        if len(found) != 1:
            raise ValueError("Original native Unicode fragment is ambiguous or missing")
        return found[0]
    fragments = {
        "publicType": unique(rb"(typedef uint32_t Py_UCS4;)", cpython["Include/unicodeobject.h"]),
        "recordType": unique(rb"(typedef struct \{.*?\} _PyUnicode_TypeRecord;)", cpython["Objects/unicodectype.c"]),
        "lookup": unique(rb"(static const _PyUnicode_TypeRecord \*\ngettyperecord\(Py_UCS4 code\)\n\{.*?\n\})", cpython["Objects/unicodectype.c"]),
    }
    content = (b"/* Exact original CPython fragments; full original notices accompany the payload. */\n"
               + fragments["publicType"] + b"\n" + fragments["recordType"] + b"\n"
               + header + b"\n" + fragments["lookup"] + b"\n")
    return content, {name: hashlib.sha256(data).hexdigest() for name, data in fragments.items()}


def native_proof(cpython, header, expected, cmake, options, sdk):
    content, fragments = fixture(cpython, header)
    compile_transcript(ROOT / "tools/python-unicode/native", {"fixture.h": content, "NOTICES.txt": cpython["LICENSE"] + b"\n" + cpython["Include/unicodeobject.h"]}, expected, cmake, options)
    return {"sdk": sdk, "transcript": expected, "originalFragmentSha256": fragments,
            "headerSha256": hashlib.sha256(header).hexdigest(), "pythonSdkLinked": False}
