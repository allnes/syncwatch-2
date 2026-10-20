"""Exercise the developer SDK's isolated CLI; this does not test an embedded runtime."""

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile


ARGUMENTS = ("-I", "-S", "-B", "-X", "utf8")
CASES = ("isolated", "ignoreEnvironment", "noUserSite", "noSite", "noBytecode", "safePath",
         "utf8Mode", "noOwnedSearchPath", "noCustomization", "poisonModuleUnavailable", "unicodeRoundTrip")
CHILD = r'''
import sys
import json
from pathlib import Path
root = Path(sys.argv[1]).resolve()
def owned(value):
    return not value or Path(value).resolve().is_relative_to(root)
try:
    import syncwatch_poison
except ModuleNotFoundError as error:
    unavailable = error.name == "syncwatch_poison"
else:
    unavailable = False
sample = root / "film-\u03bc-\u0442\u0435\u0441\u0442.txt"
text = "SyncWatch \u03bc \u0442\u0435\u0441\u0442"
sample.write_text(text, encoding="utf-8")
print(json.dumps({
    "isolated": sys.flags.isolated == 1,
    "ignoreEnvironment": sys.flags.ignore_environment == 1,
    "noUserSite": sys.flags.no_user_site == 1,
    "noSite": sys.flags.no_site == 1,
    "noBytecode": sys.dont_write_bytecode and sys.flags.dont_write_bytecode == 1,
    "safePath": sys.flags.safe_path,
    "utf8Mode": sys.flags.utf8_mode == 1 and sys.getfilesystemencoding().lower() == "utf-8",
    "noOwnedSearchPath": not any(owned(p) for p in sys.path),
    "noCustomization": not any(p in sys.modules for p in ("site", "sitecustomize", "usercustomize")),
    "poisonModuleUnavailable": unavailable,
    "unicodeRoundTrip": sample.read_text(encoding="utf-8") == text
}, sort_keys=True))
'''


def identity():
    if sys.implementation.name != "cpython" or sys.version_info < (3, 12):
        raise ValueError("The developer probe requires CPython 3.12 or newer")
    return {"implementation": sys.implementation.name, "version": platform.python_version(),
            "executableSha256": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()}


def validate(data):
    try:
        result = json.loads(data)
    except (ValueError, UnicodeError) as error:
        raise ValueError("Developer SDK probe returned invalid JSON") from error
    if not isinstance(result, dict) or set(result) != set(CASES) or any(value is not True for value in result.values()):
        raise ValueError("Developer SDK isolation checks failed")
    return {"developerSdkOnly": True, "cases": result, "nativeRuntimeBuilt": False,
            "embeddingAbiVerified": False, "runtimeReady": False}


def probe():
    identity()
    with tempfile.TemporaryDirectory(prefix="syncwatch-python-startup-") as temporary:
        root = Path(temporary) / "startup-\u03bc-\u0442\u0435\u0441\u0442"
        root.mkdir()
        poison = root / "injected"
        poison.mkdir()
        for directory in (root, poison):
            for name in ("json", "sitecustomize", "usercustomize", "syncwatch_poison"):
                (directory / (name + ".py")).write_text('raise RuntimeError("Controlled startup poison executed")\n', encoding="utf-8")
        startup = root / "startup.py"
        startup.write_text('raise RuntimeError("Controlled PYTHONSTARTUP executed")\n', encoding="utf-8")
        environment = {key: value for key, value in os.environ.items() if key.upper() in {"SYSTEMROOT", "WINDIR"}}
        environment.update(TEMP=str(root), TMP=str(root), PYTHONHOME=str(root / "missing-home"),
                           PYTHONPATH=str(poison), PYTHONUSERBASE=str(poison), PYTHONSTARTUP=str(startup),
                           PYTHONINSPECT="1", PYTHONUTF8="0")
        with tempfile.TemporaryFile() as output:
            try:
                process = subprocess.run([sys.executable, *ARGUMENTS, "-c", CHILD, str(root)],
                                         cwd=root, env=environment, stdout=output, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, timeout=30)
            except subprocess.TimeoutExpired as error:
                raise ValueError("Developer SDK isolation probe timed out") from error
            output.seek(0)
            data = output.read(4097)
        if process.returncode or len(data) > 4096:
            raise ValueError("Developer SDK isolation probe failed or exceeded its output limit")
        result = validate(data)
        if list(root.rglob("*.pyc")) or list(root.rglob("__pycache__")):
            raise ValueError("Developer SDK probe wrote unexpected bytecode")
        return result


if __name__ == "__main__":
    if sys.argv[1:] != ["identity"]:
        raise SystemExit("Expected: sdk_probe.py identity")
    print(json.dumps(identity(), sort_keys=True))
