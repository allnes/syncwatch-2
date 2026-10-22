"""Executed inside the owned source-built interpreter, never the build SDK."""

import ast
import json
import math
import os
import platform
import socket
import struct
import threading
import tokenize
import traceback
import typing
import zlib

assert sys.version_info[:3] == (3, 12, 15)
assert platform.python_implementation() == "CPython"
assert platform.python_version() == "3.12.15"
read_fd, write_fd = os.pipe()
try:
    assert os.write(write_fd, b"owned") == 5
    assert os.read(read_fd, 5) == b"owned"
finally:
    os.close(read_fd)
    os.close(write_fd)
assert isinstance(ast.parse("value = 42"), ast.Module)
assert list(tokenize.generate_tokens(iter(["value = 42"]).__next__))[0].string == "value"
assert not set(sys.builtin_module_names) & {"_ssl", "_hashlib", "_ctypes", "_sqlite3", "_random", "pyexpat", "_decimal", "_bz2", "_lzma", "_tkinter"}
assert zlib.ZLIB_VERSION == zlib.ZLIB_RUNTIME_VERSION == "1.3.2"
assert zlib.crc32(b"123456789") == 0xcbf43926
assert zlib.compress(b"hello") == bytes.fromhex("789ccb48cdc9c90700062c0215")
assert zlib.decompress(bytes.fromhex("789ccb48cdc9c90700062c0215")) == b"hello"
assert float("2.2250738585072014e-308").hex() == "0x1.0000000000000p-1022"
assert float("5e-324").hex() == "0x0.0000000000001p-1022"
assert "Straße".casefold() == "strasse" and math.isclose(math.sqrt(2) ** 2, 2)
assert all(Path(module.__file__).as_posix().startswith(Path(EXPECTED_PATHS[0]).as_posix() + "/") for module in [json, socket, threading])

payload = json.dumps({"text": "SyncWatch μ тест", "sequence": 42}, ensure_ascii=False).encode("utf-8")
left, right = socket.socketpair()
left.settimeout(5); right.settimeout(5)
observed = []
failures = []


def receive_exact(stream, size):
    result = bytearray()
    while len(result) < size:
        chunk = stream.recv(size - len(result))
        if not chunk:
            raise AssertionError("Unexpected EOF in native runtime fixture")
        result.extend(chunk)
    return bytes(result)


def worker():
    try:
        size, = struct.unpack(">I", receive_exact(right, 4))
        assert 0 < size <= 4096
        value = json.loads(receive_exact(right, size))
        observed.append(value)
        right.sendall(b"OK")
    except BaseException as error:
        failures.append(str(error))
    finally:
        right.close()


thread = threading.Thread(target=worker, daemon=True)
try:
    thread.start()
    frame = struct.pack(">I", len(payload)) + payload
    for byte in frame:
        left.sendall(bytes([byte]))
    assert receive_exact(left, 2) == b"OK"
finally:
    left.close()
    thread.join(timeout=10)
assert not thread.is_alive() and not failures
assert observed == [{"text": "SyncWatch μ тест", "sequence": 42}]
