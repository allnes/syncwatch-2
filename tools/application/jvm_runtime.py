"""Build the separately pinned Linux application JVM offline, using a boot JDK only as a tool."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tarfile
import tempfile

from receipts import ROOT, media, require_host


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def command(arguments, cwd, environment, log, timeout=180):
    log.write("\n$ " + " ".join(map(str, arguments)) + "\n")
    log.flush()
    process = subprocess.Popen(list(map(str, arguments)), cwd=cwd, env=environment, stdout=log,
                               stderr=subprocess.STDOUT, start_new_session=True)
    try:
        status = process.wait(timeout=timeout)
        if status:
            raise subprocess.CalledProcessError(status, arguments)
    except BaseException:
        # One new session owns the complete configure/make/compiler process tree.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)
        raise


def build(arguments):
    require_host("linux-x64")
    profile = json.loads((ROOT / "tools/application/jvm-profile.json").read_text())
    media(arguments.media_package, "linux-x64")
    # The boot/compiler SDK is verified in full, and never copied into the application JVM.
    import sys
    sys.path.insert(0, str(ROOT / "tools/jvm"))
    import jdk
    home = arguments.boot_jdk.resolve(strict=True)
    sdk = json.loads((ROOT / "tools/jvm/toolchains.json").read_text())
    installation = home.parent
    if jdk.verify(installation, sdk, "linux-x64") != home:
        raise ValueError("Boot JDK differs from the declared developer toolchain")
    if arguments.output.exists() or arguments.output.is_symlink():
        raise ValueError("JVM output already exists")
    if not 1 <= arguments.jobs <= 4:
        raise ValueError("Application JVM build permits one to four jobs")
    output = arguments.output.absolute()
    output.mkdir()
    try:
        with tempfile.TemporaryDirectory(prefix="sw-jvm-build-", dir=output.parent) as temporary, (output / "build.log").open("w") as log:
            work = Path(temporary)
            trees = {}
            for name, source in profile["sources"].items():
                archive = arguments.sources / (name + ".tar.gz")
                if archive.is_symlink() or sha(archive) != source["archiveSha256"]:
                    raise ValueError("JVM source archive differs from its pinned original bytes")
                tree = work / name
                tree.mkdir()
                with tarfile.open(archive) as package:
                    if package.pax_headers.get("comment") != source["revision"]:
                        raise ValueError("JVM source archive has a different Git revision")
                    package.extractall(tree, filter="data")
                trees[name] = tree
            prefix = work / "prefix"
            prefix.mkdir()
            # Reuse the source-built X11 headers/clients from the verified Media SDK.
            base = arguments.media_package.resolve(strict=True)
            environment = {key: value for key, value in os.environ.items() if key not in {
                "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "JDK_JAVAC_OPTIONS", "_JAVA_OPTIONS", "CLASSPATH",
                "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "LIBRARY_PATH", "CPATH", "LD_PRELOAD"}}
            environment.update({"PATH": str(arguments.autotools.resolve(strict=True)) + os.pathsep + environment["PATH"],
                "PKG_CONFIG_LIBDIR": str(prefix / "lib/pkgconfig"),
                "ACLOCAL_PATH": os.pathsep.join((str(arguments.xorg_macros.resolve(strict=True)),
                                                str(arguments.autotools.resolve().parent / "share/aclocal"),
                                                str(arguments.pkg_config_macros.resolve(strict=True)))),
                "CPPFLAGS": "-I" + str(base / "include"), "LDFLAGS": "-L" + str(base / "lib"),
                "LD_LIBRARY_PATH": str(prefix / "lib") + os.pathsep + str(base / "lib"),
                "SOURCE_DATE_EPOCH": "1783987200", "HTTP_PROXY": "http://127.0.0.1:9",
                "HTTPS_PROXY": "http://127.0.0.1:9", "ALL_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""})
            for name in ("m4", "autoconf", "automake", "aclocal", "autoreconf", "autom4te", "autoheader", "libtoolize"):
                environment[name.upper()] = str(arguments.autotools.resolve() / name)
            # Bind original configure modules directly to the verified source-built SDK.
            # SDK pkg-config metadata with its former installation prefix is not a runtime input.
            for name, libraries in (("FIXESEXT", "-lX11"), ("XI", "-lXext -lX11"),
                                    ("XFIXES", "-lXfixes"), ("XTST", "-lXi -lXext -lX11")):
                environment[name + "_CFLAGS"] = "-I" + str(prefix / "include") + " -I" + str(base / "include")
                environment[name + "_LIBS"] = "-L" + str(prefix / "lib") + " -L" + str(base / "lib") + " " + libraries
            for name in ("jvm-libxfixes", "jvm-libxi", "jvm-libxtst", "jvm-alsa"):
                tree = trees[name]
                for filename in ("config.guess", "config.sub"):
                    shutil.copy2(arguments.gnu_config / filename, tree / filename)
                command(["autoreconf", "-fi"], tree, environment, log)
                directory = work / (name + "-build")
                directory.mkdir()
                flags = ["--prefix=" + str(prefix), "--disable-static"]
                if name == "jvm-alsa":
                    flags += ["--disable-python", "--disable-ucm", "--disable-topology", "--disable-aload"]
                else:
                    flags += ["--disable-specs", "--without-xmlto", "--without-fop", "--without-xsltproc"]
                command([tree / "configure", *flags], directory, environment, log)
                command(["make", "-j" + str(arguments.jobs)], directory, environment, log)
                command(["make", "install"], directory, environment, log)
            # Only original build-time CUPS/Xt headers are needed. No printing toolkit is linked or bundled.
            shutil.copytree(trees["jvm-cups"] / "cups", prefix / "include/cups")
            shutil.copytree(trees["jvm-libxt"] / "include/X11", prefix / "include/X11", dirs_exist_ok=True)
            # OpenJDK accepts one X11 prefix. Overlay reviewed headers into an owned build view.
            shutil.copytree(base / "include/X11", prefix / "include/X11", dirs_exist_ok=True)
            for path in (base / "lib").glob("libX*.so*"):
                shutil.copy2(path, prefix / "lib" / path.name, follow_symlinks=True)
            configuration = work / "jdk-build"
            configuration.mkdir()
            configure = ["bash", trees["openjdk"] / "configure", "--with-boot-jdk=" + str(home),
                         "--with-debug-level=release", "--with-jvm-variants=server", "--disable-warnings-as-errors",
                         "--with-native-debug-symbols=none", "--with-num-cores=" + str(arguments.jobs),
                         "--with-memory-size=8192", "--with-freetype=bundled", "--with-zlib=bundled",
                         "--with-fontconfig=" + str(base), "--with-alsa=" + str(prefix),
                         "--with-cups=" + str(prefix), "--with-x=" + str(prefix),
                         "--with-version-pre=", "--with-version-opt=syncwatch", "--with-version-build=1",
                         "--with-vendor-name=SyncWatch", "--with-vendor-url=https://github.com/salo-group/syncwatch"]
            command(configure, configuration, environment, log)
            command(["make", "JOBS=" + str(arguments.jobs), "images"], configuration, environment, log, timeout=5400)
            built = configuration / "images/jdk"
            runtime = output / "payload"
            command([built / "bin/jlink", "--module-path", built / "jmods", "--add-modules", ",".join(profile["moduleRoots"]),
                     "--strip-debug", "--no-header-files", "--no-man-pages", "--output", runtime], work, environment, log)
            for name in ("libasound.so.2", "libXi.so.6", "libXtst.so.6"):
                shutil.copy2((prefix / "lib" / name).resolve(strict=True), runtime / "lib" / name)
            shutil.copytree(prefix / "share/alsa", runtime / "share/alsa")
            # Preserve complete corresponding original source bytes and grants, alongside jlink's module legal files.
            originals = runtime / "sources"
            originals.mkdir()
            for name in profile["sources"]:
                shutil.copy2(arguments.sources / (name + ".tar.gz"), originals)
            for name in ("LICENSE", "ADDITIONAL_LICENSE_INFO", "ASSEMBLY_EXCEPTION"):
                shutil.copy2(trees["openjdk"] / name, runtime / name)
            # Materialize legal symlinks as regular files; the application runtime receipt forbids links.
            for path in sorted(runtime.rglob("*")):
                if path.is_symlink():
                    content = path.resolve(strict=True).read_bytes()
                    path.unlink()
                    path.write_bytes(content)
            command([runtime / "bin/java", "--list-modules"], runtime, environment, log)
            report = {"schemaVersion": 1, "target": "linux-x64", "sourceRevision": profile["sources"]["openjdk"]["revision"],
                      "sourceBuilt": True, "developerSdk": False, "runtimeQualified": False,
                      "sources": profile["sources"], "modules": profile["moduleRoots"],
                      "bootJdkInventorySha256": sdk["targets"]["linux-x64"]["inventorySha256"],
                      "mediaReceiptSha256": sha(base / "build-report.json"), "configure": list(map(str, configure)),
                      "compiler": subprocess.check_output(["gcc", "--version"], text=True).splitlines()[0],
                      "compilerSha256": sha(Path(shutil.which("gcc")).resolve()),
                      "buildTools": {name: sha(arguments.autotools / name) for name in
                                     ("m4", "autoconf", "automake", "aclocal", "autoreconf", "autom4te", "autoheader", "libtoolize")},
                      "gnuConfig": {name: sha(arguments.gnu_config / name) for name in ("config.guess", "config.sub")},
                      "pkgConfigMacroSha256": sha(arguments.pkg_config_macros / "pkg.m4"),
                      "files": {path.relative_to(runtime).as_posix(): sha(path) for path in sorted(runtime.rglob("*")) if path.is_file()}}
            (runtime / "jvm-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            if arguments.retain_build_jdk:
                from candidate_tree import inventory
                sdk_report = {"schemaVersion": 1, "sourceBuilt": True,
                              "sources": profile["sources"], "configure": list(map(str, configure)),
                              "files": inventory(built)}
                (output / "build-jdk-report.json").write_text(json.dumps(sdk_report, indent=2, sort_keys=True) + "\n")
                # This reusable build SDK stays outside payload; application assembly never copies it.
                built.rename(output / "build-jdk")
    except BaseException:
        # Retain only the bounded failure log; temporary source/build/output copies are owned by this invocation.
        payload = output / "payload"
        if payload.exists():
            shutil.rmtree(payload)
        if (output / "build-jdk").exists():
            shutil.rmtree(output / "build-jdk")
        (output / "build-jdk-report.json").unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sources", "media-package", "boot-jdk", "autotools", "xorg-macros", "gnu-config", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--pkg-config-macros", type=Path, default=Path("/usr/share/aclocal"))
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--retain-build-jdk", action="store_true")
    build(parser.parse_args())
