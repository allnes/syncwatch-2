"""Probe upstream pure modules in an isolated child; never initialize the engine."""

import importlib.abc
import json
from pathlib import Path
import sys
import warnings


root = Path(sys.argv[1]).resolve()
attempts = []
# CPython 3.12 platform.py probes its Windows-only private SDK extension even
# on Linux; that build omits _wmi from stdlib_module_names. No external module
# is provided here, and the isolated source inventory contains no _wmi file.
standard_library = sys.stdlib_module_names | {"_wmi"}


class RejectExternalImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
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
