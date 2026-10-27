"""Write portable artifact metadata independently of restored-cache timestamps."""

from pathlib import Path
import json
import shutil
import zipfile


def write_origin(receipt, destination, *, run_id, run_attempt):
    origin = {"schemaVersion": 1, "kind": "native-helper",
              **{key: receipt[key] for key in ("sourceCommit", "sourceTree", "localChanges", "target")},
              "runId": run_id, "runAttempt": run_attempt}
    destination.write_text(json.dumps(origin, indent=2) + "\n", encoding="utf-8")
    return destination


def write_archive(directory: Path, attachments, destination: Path):
    entries = [("payload/" + p.relative_to(directory).as_posix(), p)
               for p in directory.rglob("*") if p.is_file()]
    entries.extend(attachments)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o100755 if name in {"payload/bin/syncwatch-helper", "payload/bin/syncwatch-helper.exe"} else 0o100644
            info.external_attr = mode << 16
            with path.open("rb") as source, archive.open(info, "w") as target:
                shutil.copyfileobj(source, target)
