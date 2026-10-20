"""Executed only inside the native SDK fixture with generated synthetic inputs."""

import sys

assert sys.flags.isolated == 1 and sys.flags.ignore_environment == 1
assert sys.flags.no_user_site == 1 and sys.flags.no_site == 1
assert sys.flags.safe_path and sys.flags.dont_write_bytecode == 1 and sys.dont_write_bytecode
assert sys.flags.utf8_mode == 1 and sys.getfilesystemencoding().lower() == "utf-8"
assert not any(name in sys.modules for name in ("site", "sitecustomize", "usercustomize"))
assert sys.path == EXPECTED_PATHS
assert sys.executable == EXPECTED_EXECUTABLE and sys._base_executable == EXPECTED_EXECUTABLE
assert sys.prefix == EXPECTED_PREFIX and sys.base_prefix == EXPECTED_PREFIX
assert sys.exec_prefix == EXPECTED_PREFIX and sys.base_exec_prefix == EXPECTED_PREFIX
assert sys._stdlib_dir == EXPECTED_STDLIB
try:
    import syncwatch_poison
except ModuleNotFoundError as error:
    assert error.name == "syncwatch_poison"
else:
    raise AssertionError("Poisoned environment/current directory was searched")
from sw_native_fixture import VALUE
assert VALUE == "SyncWatch \u03bc \u0442\u0435\u0441\u0442"
from pathlib import Path
sample = Path(OWNED_ROOT) / "film-\u03bc-\u0442\u0435\u0441\u0442.txt"
sample.write_text(VALUE, encoding="utf-8")
assert sample.read_text(encoding="utf-8") == VALUE
