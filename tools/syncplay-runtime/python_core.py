"""Configure the owned CPython core for the selected headless engine graph."""

import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/python-build"))
from native_build import build_native, sdk_identity
from source_profile import read_sources, validate


def selected_profile(target):
    profile = json.loads(Path(__file__).with_name("python-profile.json").read_text(encoding="utf-8"))
    if profile["profile"] != "headless-syncplay-python-v1" or profile["syncplayRuntimeReady"] is not False:
        raise ValueError("Unknown engine interpreter configuration")
    if target == "macos-arm64":
        profile["extensions"].update(profile["macosOnly"])
    if target == "windows-x64":
        for name in profile["posixOnly"]:
            del profile["extensions"][name]
        profile["extensions"].update(profile["windowsOnly"])
    return profile


def build(work, sources, openssl, cmake, options, sdk):
    profile = selected_profile(sdk["target"])
    validate(sources, profile)
    if sdk["target"] == "windows-x64":
        settings = {"msbuildProperties": ["/p:opensslIncludeDir=" + str(openssl / "include"),
            "/p:opensslOutDir=" + str(openssl / "lib"), "/p:SkipCopySSLDLL=true"]}
    else:
        flags = ["-I" + (openssl / "include").as_posix(), "-L" + (openssl / "lib").as_posix(), "-lssl", "-lcrypto"]
        settings = {"moduleFlags": {"_ssl": flags, "_hashlib": flags},
                    # Use upstream binascii's independent CRC implementation.
                    # Its optional auto-detected zlib must not link an OS copy.
                    "configureEnvironment": {"ac_cv_header_zlib_h": "no", "ac_cv_lib_z_gzread": "no"}}
        if sdk["target"] == "macos-arm64":
            settings["moduleFlags"]["_scproxy"] = ["-framework", "SystemConfiguration", "-framework", "CoreFoundation"]
        # Upstream's source-built freeze executables run through a system shell.
        # Use their owned loader-relative directories; environment search paths
        # are neither reliable on macOS nor an application runtime policy.
        suffix = ".3.dylib" if sdk["target"] == "macos-arm64" else ".so.3"
        for directory in [work / "lib", work / "build/lib"]:
            directory.mkdir(parents=True, exist_ok=True)
            for name in ["libssl", "libcrypto"]:
                shutil.copyfile(openssl / "lib" / (name + suffix), directory / (name + suffix))
    source, native, commands = build_native(work, sources, profile, cmake, options, sdk, settings)
    return profile, source, native, commands
