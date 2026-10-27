"""Import a native SDK artifact only for its exact source checkout and producer run."""

import argparse
import configparser
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile

from receipts import ROOT, checked_receipt, require_host

sys.path.insert(0, str(ROOT / "tools/dependencies"))
import build as dependencies
sys.path.insert(0, str(ROOT / "tools/bridge"))
from helper_sources import first_party_inputs


def validate_manifest(manifest, component, target, run_id, producer_attempt, root):
    specification = dependencies.registry(root).get(component)
    if not specification or specification["status"] != "ready" or target not in specification["targets"]:
        raise ValueError("SDK component or native target is unavailable")
    commit = dependencies.git(root, "rev-parse", "HEAD").decode().strip()
    tree = dependencies.git(root, "rev-parse", "HEAD^{tree}").decode().strip()
    if (manifest.get("schemaVersion") != 1 or manifest.get("result") != "success"
            or manifest.get("verifiedSourceCommit") != commit or manifest.get("verifiedSourceTree") != tree
            or manifest.get("verifiedLocalChanges") is not False
            or manifest.get("runId") != str(run_id) or manifest.get("runAttempt") != str(producer_attempt)):
        raise ValueError("SDK verification source or producer identity differs")
    inputs = manifest.get("inputs")
    if (not isinstance(inputs, dict) or inputs.get("schemaVersion") != 1 or inputs.get("artifactSchema") != 1
            or inputs.get("component") != component or inputs.get("platform") != target
            or inputs.get("specification") != specification or inputs.get("offlineEnvironment") != dependencies.OFFLINE
            or manifest.get("key") != hashlib.sha256(dependencies.canonical(inputs)).hexdigest()):
        raise ValueError("SDK build specification or input key differs")
    if (inputs.get("files") != dependencies.input_files(root, specification)
            or manifest.get("verificationInputs") != dependencies.input_files(root, specification, verification=True)):
        raise ValueError("SDK first-party build or verification inputs differ")
    tools = inputs.get("toolchains")
    declared = specification["targets"][target]["toolchains"]
    if (not isinstance(tools, dict) or set(tools) != set(declared)
            or any(not isinstance(tools[name], str) or not re.fullmatch(tool["pattern"], tools[name])
                   for name, tool in declared.items())):
        raise ValueError("SDK producer toolchains differ from their declared compatibility")
    system, architectures, _ = dependencies.PLATFORMS[target]
    if inputs.get("host", {}).get("system") != system or inputs.get("host", {}).get("architecture") not in architectures:
        raise ValueError("SDK producer host differs from its native target")
    config = configparser.ConfigParser(interpolation=None)
    config.read(root / ".gitmodules", encoding="utf-8")
    urls = {config[section]["path"]: config[section]["url"] for section in config.sections()}
    sources = inputs.get("sources")
    if not isinstance(sources, dict) or set(sources) != set(specification["sources"]):
        raise ValueError("SDK source graph differs")
    for name, source in specification["sources"].items():
        snapshot = sources[name]
        if (not isinstance(snapshot, dict) or snapshot.get("revision") != source["revision"]
                or snapshot.get("url") != urls[name]
                or not re.fullmatch(r"[0-9a-f]{40}", snapshot.get("tree", ""))
                or not re.fullmatch(r"[0-9a-f]{64}", snapshot.get("archiveSha256", ""))
                or snapshot.get("exports") != source.get("exports")):
            raise ValueError("SDK source pin, export or original archive identity differs")
    # Cache provenance may retain an older buildSourceCommit. Only its fresh
    # verification commit and declared inputs bind this SDK to the consumer.
    if dependencies.git(root, "diff", "--name-only", "HEAD", "--ignore-submodules=all").strip():
        raise ValueError("SDK consumer source checkout has tracked changes")


def import_dependency(archive, destination, *, component, target, run_id, producer_attempt, root=ROOT):
    require_host(target)
    if type(run_id) is not int or run_id < 1 or type(producer_attempt) is not int or producer_attempt < 1:
        raise ValueError("SDK producer run and attempt must be positive integers")
    archive, destination = Path(archive), Path(destination).absolute()
    destination = dependencies.generated_path(root, destination.relative_to(root).as_posix())
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > dependencies.MAXIMUM_ARCHIVE:
        raise ValueError("SDK archive must be a bounded regular file")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("SDK import cannot adopt an existing output")
    with zipfile.ZipFile(archive) as package:
        entry = package.getinfo("build-manifest.json")
        if entry.file_size > 8 * 1024 * 1024:
            raise ValueError("SDK manifest exceeds its bound")
        manifest = json.loads(package.read(entry))
    if not isinstance(manifest, dict):
        raise ValueError("Invalid SDK build manifest")
    validate_manifest(manifest, component, target, run_id, producer_attempt, root)
    destination.mkdir()
    try:
        with tempfile.TemporaryDirectory(prefix=".sdk-import-", dir=destination) as temporary:
            stage = Path(temporary)
            # Reuse the dependency producer's portable path, mode, inventory and
            # complete byte verification instead of a second ZIP extraction policy.
            imported = dependencies.unpack(archive, stage, manifest)
            if imported != manifest or dependencies.payload_inventory(stage) != manifest["files"]:
                raise ValueError("SDK artifact changed during import")
            validate_manifest(imported, component, target, run_id, producer_attempt, root)
            (stage / "payload").rename(destination / "payload")
            (destination / "build-manifest.json").write_text(json.dumps(imported, indent=2) + "\n", encoding="utf-8")
        return destination / "payload"
    except BaseException:
        shutil.rmtree(destination)
        raise


def import_helper(archive, destination, *, target, run_id, producer_attempt, root=ROOT):
    require_host(target)
    if type(run_id) is not int or run_id < 1 or type(producer_attempt) is not int or producer_attempt < 1:
        raise ValueError("Helper producer run and attempt must be positive integers")
    archive, destination = Path(archive), Path(destination).absolute()
    destination = dependencies.generated_path(root, destination.relative_to(root).as_posix())
    if archive.is_symlink() or not archive.is_file():
        raise ValueError("Helper artifact must be a regular file")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Helper import cannot adopt an existing output")
    commit = dependencies.git(root, "rev-parse", "HEAD").decode().strip()
    tree = dependencies.git(root, "rev-parse", "HEAD^{tree}").decode().strip()
    inputs = first_party_inputs(root)
    pins = dependencies.index(root)
    with dependencies.checked_archive(archive) as package:
        def metadata(name):
            if package.getinfo(name).file_size > 8 * 1024 * 1024:
                raise ValueError("Helper artifact metadata exceeds its bound")
            value = json.loads(package.read(name))
            if not isinstance(value, dict):
                raise ValueError("Invalid helper artifact metadata")
            return value
        origin = metadata("origin.json")
        receipt = metadata("payload/helper-report.json")
        acceptance = metadata("acceptance.json")
        if (origin.get("schemaVersion") != 1 or origin.get("kind") != "native-helper"
                or origin.get("runId") != str(run_id) or origin.get("runAttempt") != str(producer_attempt)
                or any(value.get("sourceCommit") != commit or value.get("sourceTree") != tree
                       or value.get("localChanges") is not False or value.get("target") != target
                       for value in (origin, receipt))):
            raise ValueError("Helper verification source, native target or producer identity differs")
        if (receipt.get("schemaVersion") != 1 or receipt.get("developmentHelperOnly") is not True
                or receipt.get("authenticatedInstallation") is not False or receipt.get("firstPartyInputs") != inputs
                or pins.get("3rdparty/syncplay") != ("160000", receipt.get("syncplayRevision"))
                or pins.get("3rdparty/fastjsonschema") != ("160000", receipt.get("validatorRevision"))):
            raise ValueError("Helper first-party inputs or registered source pins differ")
        receipt_bytes = package.read("payload/helper-report.json")
        session = acceptance.get("session", {})
        if (acceptance.get("sourceCommit") != commit or acceptance.get("target") != target
                or acceptance.get("helperReceiptSha256") != hashlib.sha256(receipt_bytes).hexdigest()
                or any(session.get(name) is not True for name in
                       ("coalescedFrames", "identicalReplay", "shutdown", "oversizedInputClosed"))
                or package.getinfo("native-probe.log").file_size > 4 * 1024 * 1024
                or b"SYNCWATCH_NATIVE_BRIDGE_OK" not in package.read("native-probe.log")):
            raise ValueError("Helper native acceptance does not match the payload")
        executable = "bin/syncwatch-helper" + (".exe" if target == "windows-x64" else "")
        if (not isinstance(receipt.get("files"), dict) or executable not in receipt["files"]
                or "app/syncplay-revision.txt" not in receipt["files"]):
            raise ValueError("Helper runtime closure is incomplete")
        files = {"payload/" + name: {"sha256": digest, "mode": 0o755 if name == executable else 0o644}
                 for name, digest in receipt["files"].items()}
        files["payload/helper-report.json"] = {"sha256": hashlib.sha256(receipt_bytes).hexdigest(), "mode": 0o644}
        destination.mkdir()
        try:
            with tempfile.TemporaryDirectory(prefix=".helper-import-", dir=destination) as temporary:
                stage = Path(temporary)
                dependencies.extract_payload(package, stage, files,
                                             metadata_files=("origin.json", "acceptance.json", "native-probe.log"))
                imported = checked_receipt(stage / "payload", "helper-report.json")
                if (imported != receipt or dependencies.payload_inventory(stage) != files
                        or (stage / "payload/app/syncplay-revision.txt").read_text().strip() != receipt["syncplayRevision"]
                        or first_party_inputs(root) != inputs
                        or dependencies.git(root, "rev-parse", "HEAD").decode().strip() != commit
                        or dependencies.git(root, "diff", "--name-only", "HEAD", "--ignore-submodules=all").strip()):
                    raise ValueError("Helper inputs or payload changed during import")
                (stage / "payload").rename(destination / "payload")
                for name in ("origin.json", "acceptance.json"):
                    (destination / name).write_bytes(package.read(name))
            return destination / "payload"
        except BaseException:
            shutil.rmtree(destination)
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--kind", choices=("dependency", "helper"), default="dependency")
    parser.add_argument("--component")
    parser.add_argument("--target", required=True, choices=tuple(dependencies.PLATFORMS))
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--producer-attempt", required=True, type=int)
    args = parser.parse_args()
    if args.kind == "dependency" and not args.component:
        parser.error("A dependency SDK import requires --component")
    options = dict(target=args.target, run_id=args.run_id, producer_attempt=args.producer_attempt)
    print(import_dependency(args.archive, args.output, component=args.component, **options) if args.kind == "dependency"
          else import_helper(args.archive, args.output, **options))
