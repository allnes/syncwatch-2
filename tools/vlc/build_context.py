"""Compatibility imports for the shared native build context."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native"))
from native_context import BuildContext, checksum, native_target, shell_path
