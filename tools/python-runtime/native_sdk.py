"""Identify installed CPython C development inputs; never provision or package them."""

import hashlib
import json
from pathlib import Path
import platform
import sys
import sysconfig


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def resolve():
    if (sys.implementation.name != "cpython" or not (3, 12) <= sys.version_info[:2] < (4, 0)
            or sysconfig.get_config_var("Py_GIL_DISABLED") or sysconfig.get_config_var("Py_DEBUG")):
        raise ValueError("A release, GIL-enabled CPython 3.12+ development SDK is required")
    include = Path(sysconfig.get_path("include")).resolve()
    config = Path(sysconfig.get_config_h_filename()).resolve()
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    prefix = Path(sys.base_prefix).resolve()
    if sys.platform == "win32":
        stem = f"python{sys.version_info.major}{sys.version_info.minor}"
        library = prefix / "libs" / (stem + ".lib")
        runtime = prefix / (stem + ".dll")
        extensions = prefix / "DLLs"
    else:
        name = sysconfig.get_config_var("LDLIBRARY")
        if not name:
            raise ValueError("The development SDK has no shared embedding library")
        candidates = [Path(sysconfig.get_config_var("LIBDIR") or "") / name]
        if sysconfig.get_config_var("PYTHONFRAMEWORKPREFIX"):
            candidates.append(Path(sysconfig.get_config_var("PYTHONFRAMEWORKPREFIX")) / name)
        library = next((p.resolve() for p in candidates if p.is_file()), None)
        runtime = library
        extensions = Path(sysconfig.get_config_var("DESTSHARED") or stdlib / "lib-dynload").resolve()
    if not all(p is not None and p.is_file() for p in (library, runtime, config, include / "Python.h")):
        raise ValueError("The development SDK is missing embedding headers or libraries")
    headers = {p.relative_to(include).as_posix(): sha(p) for p in sorted(include.rglob("*.h")) if p.is_file()}
    paths = {"include": include, "library": library, "runtime": runtime, "stdlib": stdlib,
             "prefix": prefix, "extensions": extensions}
    identity = {"developerSdkOnly": True, "version": platform.python_version(), "executableSha256": sha(sys.executable),
                "headersSha256": hashlib.sha256(json.dumps(headers, sort_keys=True).encode()).hexdigest(),
                "headerCount": len(headers), "configHeaderSha256": sha(config),
                "linkLibrarySha256": sha(library), "sdkRuntimeLibrarySha256": sha(runtime)}
    return paths, identity
