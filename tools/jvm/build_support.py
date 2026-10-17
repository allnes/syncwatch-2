"""Deterministic JVM archive and isolated developer-tool helpers."""

import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


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


def java_environment():
    ambient = {"JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "JDK_JAVAC_OPTIONS", "_JAVA_OPTIONS", "CLASSPATH"}
    return {k: v for k, v in os.environ.items() if k.upper() not in ambient}


def run(arguments, directory):
    try:
        return subprocess.check_output(arguments, cwd=directory, env=java_environment(), stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as error:
        print(error.output, file=sys.stderr)
        raise
