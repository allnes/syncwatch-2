"""Build the X11 clients loaded dynamically by the Linux application's AWT runtime."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile

from receipts import ROOT, media, require_host
from jvm_runtime import command, sha
from source_profile import read

sys.path.insert(0, str(ROOT / "tools/native"))
sys.path.insert(0, str(ROOT / "tools/dependencies"))
from native_context import BuildContext
from native_x11 import autotools, SHARED, NO_SPECS
from build import OFFLINE


class ClientContext(BuildContext):
    def run(self, label, arguments, cwd=None, *, timeout=180):
        with (self.logs / (label + ".log")).open("w") as log:
            command(arguments, cwd or self.work, self.env, log, timeout)
        self.commands[label] = {"arguments": list(map(str, arguments)), "cwd": str(cwd or self.work)}


def build(arguments):
    require_host("linux-x64")
    profile = read(ROOT / "tools/application/linux-clients.json")
    media(arguments.media_package, "linux-x64")
    output = arguments.output.absolute()
    output.mkdir(exist_ok=False)
    try:
        with tempfile.TemporaryDirectory(prefix="sw-x11-clients-", dir=output.parent) as temporary:
            work = Path(temporary)
            tools = work / "tool-sdk"
            auxiliary = tools / "usr/share/misc"
            auxiliary.mkdir(parents=True)
            macros = tools / "usr/share/aclocal"
            macros.mkdir()
            for name in ("config.guess", "config.sub"):
                shutil.copy2(arguments.gnu_config / name, auxiliary / name)
            shutil.copy2(arguments.xorg_macros / "xorg-macros.m4", macros)
            os.environ["SYNCWATCH_VLC_AUTOTOOLS_ROOT"] = str(arguments.autotools.resolve().parent.parent)
            os.environ["SYNCWATCH_VLC_EXTRA_TOOLS_ROOT"] = str(tools)
            context = ClientContext(work, profile["sourceDateEpoch"])
            context.env.update(OFFLINE)
            base = arguments.media_package.resolve(strict=True)
            context.env.update(PKG_CONFIG_LIBDIR=str(context.prefix / "lib/pkgconfig"), PKG_CONFIG_PATH="")
            context.env["LD_LIBRARY_PATH"] = str(context.prefix / "lib") + os.pathsep + str(base / "lib")
            for key in ("CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "LIBRARY_PATH"):
                context.env.pop(key, None)
            context.env["CPPFLAGS"] += " -I" + str(base / "include")
            context.env["LDFLAGS"] += " -L" + str(base / "lib")
            for name, libraries in (("FIXESEXT", "-lX11"), ("XCURSOR", "-lXrender -lXfixes -lX11"), ("XINERAMA", "-lXext -lX11")):
                context.env[name + "_CFLAGS"] = "-I" + str(context.prefix / "include") + " -I" + str(base / "include")
                context.env[name + "_LIBS"] = "-L" + str(context.prefix / "lib") + " -L" + str(base / "lib") + " " + libraries
            trees = {}
            for name, source in profile["sources"].items():
                archive = arguments.sources / (name + ".tar")
                if archive.is_symlink() or sha(archive) != source["archiveSha256"]:
                    raise ValueError("X11 client source archive differs from the pinned original Git blobs")
                tree = work / name
                tree.mkdir()
                with tarfile.open(archive) as package:
                    if package.pax_headers.get("comment") != source["revision"]:
                        raise ValueError("X11 source archive has a different Git revision")
                    package.extractall(tree, filter="data")
                trees[name] = tree
            try:
                for name in profile["buildOrder"]:
                    autotools(context, trees, name, [*SHARED, *NO_SPECS])
                payload = output / "payload"
                (payload / "lib").mkdir(parents=True)
                for name in profile["runtimeLibraries"]:
                    destination = payload / "lib" / name
                    shutil.copy2((context.prefix / "lib" / name).resolve(strict=True), destination)
                    context.run("relocate-" + name, [arguments.patchelf, "--set-rpath", "$ORIGIN", destination])
                originals = payload / "sources"
                originals.mkdir()
                notices = []
                for name, source in profile["sources"].items():
                    shutil.copy2(arguments.sources / (name + ".tar"), originals)
                    for grant in source["notices"]:
                        destination = payload / "notices" / name / grant
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(trees[name] / grant, destination)
                        notices.append(name + "/" + grant + "\n" + destination.read_text())
                (payload / "THIRD-PARTY-NOTICES.txt").write_text("\n\n".join(notices))
                report = {"schemaVersion": 1, "target": "linux-x64", "sourceBuilt": True,
                          "sources": profile["sources"], "mediaReceiptSha256": sha(base / "build-report.json"),
                          "commands": context.commands,
                          "tools": {name: sha(Path(context.tool(name)).resolve()) for name in ("gcc", "make", "autoconf", "automake", "libtoolize", "m4")},
                          "patchelfSha256": sha(arguments.patchelf),
                          "files": {path.relative_to(payload).as_posix(): sha(path) for path in sorted(payload.rglob("*")) if path.is_file()}}
                (payload / "clients-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            finally:
                shutil.copytree(context.logs, output / "logs")
    except BaseException:
        if (output / "payload").exists():
            shutil.rmtree(output / "payload")
        raise
    print("Source-built dynamic X11 client package:", payload)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sources", "media-package", "autotools", "xorg-macros", "gnu-config", "patchelf", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    build(parser.parse_args())
