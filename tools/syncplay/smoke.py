"""Probe upstream pure modules in an isolated child; never initialize the engine."""

import importlib.abc
import importlib.machinery
import json
from pathlib import Path
import sys
import warnings


root = Path(sys.argv[1]).resolve()
attempts = []
# Optional interpreter probes can be absent from stdlib_module_names: platform
# checks _wmi and traceback checks generated metadata on newer CPython builds.
# Resolve these only against the isolated interpreter paths, before adding the
# source artifact. An artifact must never supply an interpreter metadata module.
standard_library = sys.stdlib_module_names
standard_library_paths = tuple(sys.path)
optional_interpreter_modules = {"_wmi", "_missing_stdlib_info"}


class RejectExternalImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in optional_interpreter_modules and fullname not in standard_library:
            spec = importlib.machinery.PathFinder.find_spec(fullname, standard_library_paths)
            if spec is None:
                raise ModuleNotFoundError("Optional interpreter module is unavailable", name=fullname)
            return spec
        if fullname.split(".")[0] not in standard_library | {"syncplay"}:
            attempts.append("import:" + fullname)
            raise ImportError("External modules are unavailable in a source-only probe")


def audit(event, _arguments):
    if event.startswith(("socket.", "subprocess.")) or event in {"os.system", "os.posix_spawn", "os.fork", "os.exec"}:
        attempts.append(event)
        raise RuntimeError("Source-only probes cannot use a network or launch processes")


sys.addaudithook(audit)
sys.meta_path.insert(0, RejectExternalImports())
sys.path.insert(0, str(root))
warnings.filterwarnings("ignore", category=DeprecationWarning)

from syncplay import constants, messages, utils, version

for module in (constants, messages, utils):
    if not Path(module.__file__).resolve().is_relative_to(root):
        raise RuntimeError("Upstream module escaped the exact source artifact")
if version != sys.argv[2]:
    raise RuntimeError("Unexpected upstream version")
languages = messages.getLanguages()
for language in ("en", "ru"):
    messages.setLanguage(language)
    if not messages.getMessage("LANGUAGE") or not messages.getMessage("startTLS-not-supported-server"):
        raise RuntimeError("Upstream messages were not loaded")
if not utils.meetsMinVersion("1.7.6", "1.7.0") or utils.meetsMinVersion("1.6.9", "1.7.0"):
    raise RuntimeError("Upstream version comparison changed")
if attempts:
    raise RuntimeError("Source-only probe attempted unavailable operations: " + repr(attempts))
print(json.dumps({"runtimeReady": False, "attempts": attempts, "languages": sorted(languages),
                  "modules": ["syncplay.constants", "syncplay.messages", "syncplay.utils"],
                  "engineInitialized": False}, sort_keys=True))
