"""Query the owned codec libraries' actual licensing and configuration APIs."""

import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import re


def verify(package, expected_version):
    system = platform.system()
    libraries = package / ("bin" if system == "Windows" else "lib")
    directory = os.add_dll_directory(str(libraries)) if system == "Windows" else None
    handles, result = [], {}
    try:
        # Load utilities first, using only exact owned SONAME paths.
        for component in ["avutil", "avcodec", "avformat"]:
            macro = "LIB" + component.upper() + "_VERSION_MAJOR"
            header = (package / "include" / ("lib" + component) / "version_major.h")
            if not header.exists():
                header = header.with_name("version.h")
            major = re.search(r"#define\s+" + macro + r"\s+(\d+)", header.read_text())[1]
            filename = ({"Windows": component + "-" + major + ".dll",
                         "Darwin": "lib" + component + "." + major + ".dylib",
                         "Linux": "lib" + component + ".so." + major})[system]
            path = libraries / filename
            handle = ctypes.CDLL(str(path), **({"winmode": 0xD00} if system == "Windows" else {}))
            handles.append(handle)
            values = {}
            for field in ["license", "configuration"]:
                function = getattr(handle, component + "_" + field)
                function.argtypes, function.restype = [], ctypes.c_char_p
                values[field] = function().decode("utf-8")
            if values["license"] != "LGPL version 2.1 or later":
                raise ValueError("Codec runtime has an unapproved license: " + component)
            configuration = values["configuration"]
            if (not all(flag in configuration.split() for flag in ["--disable-gpl", "--disable-version3", "--disable-nonfree", "--disable-autodetect"])
                    or any(flag in configuration.split() for flag in ["--enable-gpl", "--enable-version3", "--enable-nonfree"])):
                raise ValueError("Actual codec binary has an unapproved build configuration")
            result[component] = {"file": filename, **values}
        function = handles[0].av_version_info
        function.argtypes, function.restype = [], ctypes.c_char_p
        actual = function().decode("ascii")
        if actual != expected_version:
            raise ValueError("Codec binary does not match its original release")
        return {"version": actual, "libraries": result}
    finally:
        if directory:
            directory.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("expected_version")
    args = parser.parse_args()
    print(json.dumps(verify(args.package.resolve(), args.expected_version), sort_keys=True))
