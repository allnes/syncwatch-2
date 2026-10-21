"""Retain the compiler SDK's complete original runtime/support legal material."""

from pathlib import PurePosixPath
import tarfile

from toolchains import resolve, specification


def rust_notices():
    home, identity = resolve()
    spec, target = specification()
    result = {}
    for name in spec["targets"][target]["components"]:
        # resolve() already matched each archive to its original vendor SHA256.
        with tarfile.open(home.parent / "archives" / (name + ".tar.xz")) as archive:
            for entry in archive:
                if not entry.isfile():
                    continue
                path = PurePosixPath(entry.name)
                relative = "/".join(path.parts[1:])
                if (path.name.startswith(("LICENSE", "COPYRIGHT", "NOTICE"))
                        or "/share/doc/rust/licenses/" in relative):
                    result["notices/rust-sdk/" + name + "/" + relative] = archive.extractfile(entry).read()
    if not result:
        raise ValueError("Rust SDK original grants are missing")
    return result
