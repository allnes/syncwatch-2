"""Compatibility imports for shared original Fontconfig configuration."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native"))
from native_fonts import contents, default_files
