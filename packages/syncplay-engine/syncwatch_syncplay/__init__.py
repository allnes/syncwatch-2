"""Headless adapters for the pinned upstream Syncplay engine."""

import os
from pathlib import Path
import sys

# Native Python extensions use Windows' restricted DLL loader. Retain the
# directory handle for this owned package rather than consulting PATH/CWD.
_dll_directory = os.add_dll_directory(str(Path(__file__).resolve().parent.parent)) if sys.platform == "win32" else None
