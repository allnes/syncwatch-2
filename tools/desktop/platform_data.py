"""Retain source-built X11 data and locate owned client resources after relocation."""

import hashlib
import json
import re
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def configured(prefix):
    files = {}
    for source in sorted((prefix / "share/X11").rglob("*")):
        if not source.is_file():
            continue
        if not source.resolve().is_relative_to(prefix.resolve()):
            raise ValueError("X11 runtime data points outside its source-built prefix")
        files[source.relative_to(prefix).as_posix()] = source.read_bytes()
    base = "share/X11/locale/en_US.UTF-8/Compose"
    if base not in files:
        raise ValueError("Original X11 UTF-8 Compose table is missing")
    include = b'include "' + str(prefix / base).encode() + b'"\n'
    note = b"# SyncWatch configured: expanded original UTF-8 Compose include for relocation.\n"
    # These upstream locale files include the common table using the configured
    # installation prefix. Expand exactly that known include, retaining all rules
    # and copyright bytes; do not invent another path expansion in the XIM parser.
    for name, data in files.items():
        references = re.findall(rb'^\s*include\s+"([^"\r\n]+)"', data, re.M) if name.endswith("/Compose") else []
        if references:
            if name == base or len(references) != 1 or data.count(include) != 1:
                raise ValueError("Review an unexpected X11 runtime resource reference")
            files[name] = data.replace(include, note + files[base] + b"\n")
    if any(str(prefix).encode() in data for data in files.values()):
        raise ValueError("X11 runtime data retains a temporary build prefix")
    return files


def package(prefix, payload, profile):
    files = configured(prefix)
    actual = {name: digest(data) for name, data in files.items()}
    expected = profile["platformData"]
    if actual != expected:
        differences = {"missing": sorted(expected.keys() - actual.keys()),
                       "unexpected": sorted(actual.keys() - expected.keys()),
                       "changed": {name: {"expected": expected[name], "actual": actual[name], "bytes": len(files[name])}
                                   for name in sorted(actual.keys() & expected.keys()) if actual[name] != expected[name]}}
        raise ValueError("Generated X11 runtime data differs from its reviewed source profile: "
                         + json.dumps(differences, sort_keys=True))
    for name, data in files.items():
        target = payload / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def verify(payload, profile):
    if any(not (payload / name).is_file() or (payload / name).is_symlink()
           or digest((payload / name).read_bytes()) != pin for name, pin in profile["platformData"].items()):
        raise ValueError("Owned X11 runtime data is missing or changed")


def environment(payload):
    payload = Path(payload).resolve()
    values = {"LD_LIBRARY_PATH": str(payload / "runtime"),
              "XLOCALEDIR": str(payload / "share/X11/locale"),
              "FONTCONFIG_FILE": str(payload / "share/fonts/fonts.conf"),
              "FONTCONFIG_PATH": str(payload / "share/fonts")}
    for variable, filename in (("XERRORDB", "XErrorDB"), ("XCMSDB", "Xcms.txt"), ("XKEYSYMDB", "XKeysymDB")):
        path = payload / "share/X11" / filename
        if path.is_file():
            values[variable] = str(path)
    return values
