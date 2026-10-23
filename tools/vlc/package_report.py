"""Bind a native payload to exact sources and reject changed or extra members."""

import json

from source_files import digest, encoded

REPORT = "build-report.json"


def inventory(package):
    files = {}
    for path in sorted(package.rglob("*")):
        if path.is_symlink():
            raise ValueError("Native media packages require regular files")
        if path.is_file():
            name = path.relative_to(package).as_posix()
            if name != REPORT:
                files[name] = digest(path.read_bytes())
    if not files:
        raise ValueError("Native media package is empty")
    return files


def create(package, sdk, sources, imports, proof, codec):
    report = {"schemaVersion": 1, "profile": "native-decoder-v1", "sdk": sdk,
              "sources": sources, "imports": imports, "proof": proof, "codec": codec,
              "physicalOutputAccepted": False, "applicationIntegrationReady": False,
              "hardwareH264BackwardSeekAccepted": False, "files": inventory(package)}
    (package / REPORT).write_bytes(encoded(report))
    return report


def verify(package, sdk, sources, original_contents):
    path = package / REPORT
    if not path.is_file() or path.is_symlink():
        raise ValueError("Missing regular native media build report")
    report = json.loads(path.read_bytes())
    if (report.get("schemaVersion") != 1 or report.get("profile") != "native-decoder-v1" or
            report.get("sdk") != sdk or report.get("sources") != sources or
            any(report.get(key) is not False for key in ["physicalOutputAccepted", "applicationIntegrationReady",
                                                       "hardwareH264BackwardSeekAccepted"]) or
            report.get("files") != inventory(package)):
        raise ValueError("Native media payload, source or SDK identity changed")
    for name, data in original_contents.items():
        if not (package / name).is_file() or (package / name).read_bytes() != data:
            raise ValueError("Original media source, recipe or grant changed: " + name)
    return report
