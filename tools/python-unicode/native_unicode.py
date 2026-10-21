"""Compile original table fragments with the installed C SDK, then compare all slots."""

import hashlib
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/compression"))
from toolchain import resolve


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
    with tempfile.TemporaryDirectory(prefix="sw-unicode-") as temporary:
        work = Path(temporary).resolve()
        (work / "fixture.h").write_bytes(content)
        build = work / "build"
        subprocess.run([cmake, "-S", (ROOT / "tools/python-unicode/native").as_posix(), "-B", build.as_posix(),
                        *options, "-DCMAKE_BUILD_TYPE=Release", "-DSYNCWATCH_FIXTURE=" + work.as_posix()], check=True, timeout=60)
        subprocess.run([cmake, "--build", build.as_posix(), "--config", "Release", "--parallel", "2"], check=True, timeout=120)
        executable = Path((build / "probe-Release.txt").read_text(encoding="utf-8"))
        transcript = work / "transcript.bin"
        with transcript.open("wb") as output:
            process = subprocess.run([str(executable)], stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.PIPE, timeout=30)
        if process.returncode or process.stderr or transcript.stat().st_size != expected["bytes"]:
            raise ValueError("Native Unicode transcript failed or has an unexpected size")
        with transcript.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected["sha256"]:
            raise ValueError("Native Unicode transcript differs from the independent source oracle")
    return {"sdk": sdk, "transcript": expected, "originalFragmentSha256": fragments,
            "headerSha256": hashlib.sha256(header).hexdigest(), "pythonSdkLinked": False}
