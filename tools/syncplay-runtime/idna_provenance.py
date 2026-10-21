"""Reproduce both original IDNA tables from pinned Unicode data, offline."""

import os
from pathlib import Path
import shutil
import subprocess
import sys


def verify(paths, work):
    data = work / "idna-data"
    output = work / "idna-generated"
    data.mkdir()
    output.mkdir()
    source = paths["idna-unicode-data"] / "unicodetools/data"
    ucd = source / "ucd/18.0.0"
    for original in ucd.rglob("*.txt"):
        destination = data / original.relative_to(ucd)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
    for original in (source / "idna/18.0.0").glob("*.txt"):
        shutil.copyfile(original, data / original.name)
    environment = os.environ.copy()
    environment.update(PYTHONPATH=str(paths["idna"]), PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    result = subprocess.run([sys.executable, "-X", "utf8", "-S", "-B", str(paths["idna"] / "tools/idna-data"),
        "make-libdata", "--version", "18.0.0", "--source", str(data), "--dir", str(output),
        "--no-cache"], cwd=work, env=environment, capture_output=True, timeout=180)
    if result.returncode:
        raise ValueError("Offline IDNA provenance regeneration failed: " + result.stderr[-4096:].decode(errors="replace"))
    for name in ["idnadata.py", "uts46data.py"]:
        if (output / name).read_bytes() != (paths["idna"] / "idna" / name).read_bytes():
            raise ValueError("Generated Unicode data differs from the pinned original IDNA table")
    return {"unicode": "18.0.0", "originalTablesReproduced": ["idnadata.py", "uts46data.py"], "offline": True}
