"""Build an owned test module against the real static package and verified hash archive."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/compression"))
from toolchain import resolve


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def execute(args):
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(args, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, timeout=600)
        output.seek(0);data = output.read(262145)
    if result.returncode or len(data) > 262144:
        raise ValueError("Native package build failed or exceeded diagnostic bounds:\n" + data[-16384:].decode("utf-8", errors="replace"))


def build(root):
    cmake, options, sdk = resolve()
    execute([sys.executable, "tools/dependencies/build.py", "build", "--component", "hacl-hash", "--platform", sdk["target"]])
    artifact = ROOT / "artifacts/dependencies/hacl-hash" / sdk["target"]
    with zipfile.ZipFile(artifact / "artifact.zip") as archive:
        manifest_bytes = archive.read("build-manifest.json")
        manifest = json.loads(manifest_bytes)
    # The prerequisite driver recompiled and verified its accepted payload.
    if manifest["result"] != "success" or manifest["inputs"]["platform"] != sdk["target"]:
        raise ValueError("Native hash prerequisite was not verified")
    directory = root / "build"
    execute([cmake, "-S", (ROOT / "tools/python-package").as_posix(), "-B", directory.as_posix(), *options,
             "-DCMAKE_BUILD_TYPE=Release", "-DSYNCWATCH_ROOT=" + ROOT.as_posix(), "-DSYNCWATCH_HASH=" + (artifact / "payload").as_posix()])
    execute([cmake, "--build", directory.as_posix(), "--config", "Release", "--parallel", "2"])
    module = Path((directory / "module-Release.txt").read_text(encoding="utf-8"))
    library = Path((directory / "library-Release.txt").read_text(encoding="utf-8"))
    paths = [p for directory in [ROOT/"packages/python-package", ROOT/"tools/python-package"] for p in directory.rglob("*")
             if p.is_file() and p.suffix in {".c", ".h", ".py", ".txt", ".toml", ".json"}]
    paths += [ROOT/"packages/python-startup/startup.h", ROOT/"packages/python-startup/policy.generated.h",
              ROOT/"tools/python-runtime/profile.json", ROOT/"tools/compression/toolchain.py"]
    return module, {"compiler": sdk, "hashArtifactKey": manifest["key"], "hashManifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
                    "staticLibrarySha256": sha(library), "testModuleSha256": sha(module),
                    "firstPartyFiles": {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)},
                    "pinnedRuntimeBuilt": False, "pinnedEmbeddingAbiVerified": False, "runtimeReady": False,
                    "testRuntimeDistributed": False}
