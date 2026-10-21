"""Own a disposable C SDK build and compare its fixed binary transcript."""

import hashlib
from pathlib import Path
import subprocess
import tempfile


def compile_transcript(recipe, files, expected, cmake, options):
    if not 0 < expected["bytes"] <= 64 * 1024 * 1024:
        raise ValueError("Native transcript size is outside the supported profile")
    with tempfile.TemporaryDirectory(prefix="sw-native-c-") as temporary:
        work = Path(temporary).resolve()
        for name, data in files.items():
            if not name or "\\" in name or Path(name).name != name or name in {".", ".."}:
                raise ValueError("Native fixtures require simple owned filenames")
            (work / name).write_bytes(data)
        build = work / "build"
        subprocess.run([cmake, "-S", recipe.as_posix(), "-B", build.as_posix(), *options,
                        "-DCMAKE_BUILD_TYPE=Release", "-DSYNCWATCH_FIXTURE=" + work.as_posix()], check=True, timeout=60)
        subprocess.run([cmake, "--build", build.as_posix(), "--config", "Release", "--parallel", "2"], check=True, timeout=120)
        executable = Path((build / "probe-Release.txt").read_text(encoding="utf-8"))
        transcript = work / "transcript.bin"
        with transcript.open("wb") as output:
            process = subprocess.run([str(executable)], stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.PIPE, timeout=30)
        if process.returncode or process.stderr or transcript.stat().st_size != expected["bytes"]:
            raise ValueError("Native C transcript failed or has an unexpected size")
        with transcript.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected["sha256"]:
            raise ValueError("Native C transcript differs from the independent source oracle")
