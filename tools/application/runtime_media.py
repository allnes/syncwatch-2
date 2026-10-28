"""Qualify unchanged Linux JVM linkage when only the media plugins change."""

from dataclasses import dataclass
import hashlib
from pathlib import Path

from receipts import media


@dataclass(frozen=True)
class Compatibility:
    report: dict
    build_receipt: bytes


def linkage_files(receipt):
    # Conservatively compare all headers, native libraries and shared data used
    # by the build. VLC's dynamically selected plugins are not JVM/X11 inputs.
    return {name: digest for name, digest in receipt["files"].items()
            if name.startswith(("include/", "lib/", "share/"))
            and not name.startswith("lib/vlc/plugins/")}


def qualify(package, build_package, runtime, clients):
    wanted = runtime["mediaReceiptSha256"]
    if wanted != clients["mediaReceiptSha256"]:
        raise ValueError("JVM and X11 clients have different original media build inputs")
    current = media(package, "linux-x64")
    current_hash = hashlib.sha256((package / "build-report.json").read_bytes()).hexdigest()
    if wanted == current_hash:
        return None
    if build_package is None:
        raise ValueError("Changed media SDK requires --runtime-build-media for exact linkage verification")
    build_package = Path(build_package).resolve(strict=True)
    original = media(build_package, "linux-x64")
    original_bytes = (build_package / "build-report.json").read_bytes()
    if hashlib.sha256(original_bytes).hexdigest() != wanted:
        raise ValueError("Original media SDK differs from the JVM/X11 build receipt")
    inputs = linkage_files(original)
    if (not inputs or not any(name.startswith("include/") for name in inputs)
            or not any(name.startswith("lib/") for name in inputs)
            or inputs != linkage_files(current) or original["sources"] != current["sources"]):
        raise ValueError("Native JVM/X11 headers, libraries, data or original sources changed; rebuild the runtimes")
    return Compatibility({"schemaVersion": 1, "target": "linux-x64",
        "originalMediaReceiptSha256": wanted, "currentMediaReceiptSha256": current_hash,
        "originalSourcesUnchanged": True, "linkageInputsUnchanged": inputs}, original_bytes)
