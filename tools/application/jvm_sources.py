"""Export reviewed original Git blobs for the Linux application JVM source build."""

import argparse
import gzip
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
from source_profile import read

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/dependencies"))
import build as dependencies


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def export(destination, profile_path=ROOT / "tools/application/jvm-profile.json"):
    profile = read(profile_path)
    destination.mkdir(exist_ok=False)
    try:
        for name, specification in profile["sources"].items():
            source = ROOT / specification["path"]
            pin = dependencies.index(ROOT).get(specification["path"])
            if (pin != ("160000", specification["revision"])
                    or dependencies.git(source, "rev-parse", "HEAD").decode().strip() != specification["revision"]
                    or dependencies.git(source, "rev-parse", "HEAD^{tree}").decode().strip() != specification["tree"]
                    or dependencies.git(source, "status", "--porcelain").strip()):
                raise ValueError("JVM source differs from its clean registered Git pin")
            entries = dependencies.exported_entries(source, specification["exports"])
            with tempfile.TemporaryDirectory(prefix="sw-jvm-source-") as temporary:
                archive = Path(temporary) / "original.tar"
                dependencies.export_original_blobs(source, archive, entries, specification["revision"])
                dependencies.verify_source_export(archive, entries, specification["revision"], specification["notices"])
                format_ = specification.get("archiveFormat", "tar.gz")
                if format_ not in {"tar", "tar.gz"}:
                    raise ValueError("Unsupported original source archive format")
                output = destination / (name + "." + format_)
                if format_ == "tar":
                    shutil.copy2(archive, output)
                else:
                    with output.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed, archive.open("rb") as data:
                        shutil.copyfileobj(data, compressed)
            if sha(output) != specification["archiveSha256"]:
                raise ValueError("Original JVM source archive differs from its reviewed digest")
            print(name + ": original sources verified", flush=True)
    except BaseException:
        shutil.rmtree(destination)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--profile", type=Path, default=ROOT / "tools/application/jvm-profile.json")
    args = parser.parse_args()
    export(args.output, args.profile)
