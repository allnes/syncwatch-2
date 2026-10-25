"""Link original JNI objects and reject undeclared ELF client imports."""

from pathlib import Path
import hashlib
import re
import shutil
import subprocess

import platform_data

ROOT = Path(__file__).resolve().parents[2]
# The compiler runtime and C ABI are OS/developer SDK services, never copied into the payload.
SDK_IMPORTS = {"libc.so.6", "libm.so.6", "libpthread.so.0", "libdl.so.2", "librt.so.1",
               "libgcc_s.so.1", "libstdc++.so.6", "ld-linux-x86-64.so.2"}
LIBRARY = "libskiko-linux-x64.so"
LINK_CLIENTS = {"libGL.so.1", "libX11.so.6", "libfontconfig.so.1"}
# These exact unversioned names come from the original Skiko xrandr/theme loaders.
DYNAMIC_CLIENTS = {"libXrandr.so", "libdbus-1.so"}
FAULT_CASES = ("missing-client", "foreign-runpath", "foreign-import", "incompatible-elf", "symbolic-alias", "missing-locale-data")


def dynamic(path):
    text = subprocess.check_output(["readelf", "-d", str(path)], text=True)
    return (re.findall(r"\(NEEDED\).*?\[(.*?)\]", text),
            re.findall(r"\(SONAME\).*?\[(.*?)\]", text))


def public_symbols(path):
    return set(subprocess.check_output(["nm", "-D", "--defined-only", "--format=just-symbols", str(path)], text=True).splitlines())


def symbol_digest(names):
    return hashlib.sha256(("\n".join(sorted(names)) + "\n").encode()).hexdigest()


def select_clients(prefix):
    installed = {p.name: p for p in (prefix / "lib").glob("*.so*") if p.is_file()}
    selected, pending = set(), list(LINK_CLIENTS | DYNAMIC_CLIENTS)
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        if name not in installed or not installed[name].resolve().is_relative_to(prefix.resolve()):
            raise ValueError("Required client is absent or outside the owned prefix: " + name)
        selected.add(name)
        imports, identities = dynamic(installed[name])
        pending.extend(n for n in imports + identities if n not in SDK_IMPORTS and n not in selected)
    return {name: installed[name] for name in sorted(selected)}


def exported(context, paths):
    names = set()
    for index, path in enumerate(paths):
        text = context.run("exports-" + str(index), ["nm", "-g", "--defined-only", "--format=just-symbols", path], output=True).decode()
        names.update(name for name in text.splitlines() if re.fullmatch(r"(?:Java_|JNI_)[A-Za-z_0-9.$@]*", name))
    if not names:
        raise ValueError("Original JNI objects export no entry points")
    return names


def build(context, payload, clients):
    directory = payload / "runtime"
    directory.mkdir()
    for name, source in select_clients(clients.prefix).items():
        shutil.copy2(source.resolve(), directory / name)
    objects = sorted((payload / "objects").rglob("*.o"))
    archives = sorted((payload / "lib").glob("*.a"))
    names = exported(context, [*objects, *archives])
    version = context.work / "native-exports.map"
    version.write_text("{\n global:\n" + "".join("  " + name + ";\n" for name in sorted(names)) + " local: *;\n};\n")
    context.run("native-link", ["g++", "-shared", "-Wl,-z,defs,-z,relro,-z,now", "-Wl,--version-script=" + str(version),
        "-o", directory / LIBRARY, *objects, "-Wl,--start-group", *archives, "-Wl,--end-group",
        "-L" + str(directory), "-Wl,-rpath-link," + str(directory), "-l:libfontconfig.so.1", "-l:libGL.so.1", "-l:libX11.so.6", "-ldl", "-pthread"])
    for index, path in enumerate(sorted(directory.iterdir())):
        context.run("runtime-rpath-" + str(index), [clients.tool("patchelf"), "--set-rpath", "$ORIGIN", path])
    actual = set(context.run("native-exported-symbols", ["nm", "-D", "--defined-only", "--format=just-symbols", directory / LIBRARY], output=True).decode().splitlines())
    if names != actual:
        raise ValueError("Linked JNI symbols differ from their original objects")
    return {"exports": len(names), "exportDigest": symbol_digest(names), "imports": audit(directory)}


def audit(directory):
    paths = sorted(directory.iterdir())
    if not paths or any(not p.is_file() or p.is_symlink() or not re.fullmatch(r"lib[A-Za-z0-9_.+-]+\.so(?:\.[0-9]+)*", p.name) for p in paths):
        raise ValueError("Native runtime requires regular ELF libraries and aliases")
    owned = {p.name for p in paths}
    if not (LINK_CLIENTS | DYNAMIC_CLIENTS | {LIBRARY}) <= owned:
        raise ValueError("Required linked or dynamic native client is missing")
    report = {}
    for path in paths:
        header = subprocess.check_output(["readelf", "-h", str(path)], text=True)
        if not all(value in header for value in ("ELF64", "DYN", "Advanced Micro Devices X86-64")):
            raise ValueError("Native runtime contains an incompatible ELF: " + path.name)
        dynamic = subprocess.check_output(["readelf", "-d", str(path)], text=True)
        rpaths = re.findall(r"\((?:RPATH|RUNPATH)\).*?\[(.*?)\]", dynamic)
        if rpaths != ["$ORIGIN"]:
            raise ValueError("Native runtime contains a foreign runpath: " + path.name)
        imports = re.findall(r"\(NEEDED\).*?\[(.*?)\]", dynamic)
        for name in imports:
            if name not in owned and name not in SDK_IMPORTS:
                raise ValueError("Undeclared native import " + path.name + " -> " + name)
        report[path.name] = imports
    return report


def probe(context, payload):
    binary = context.work / "linked-native-consumer"
    context.run("linked-consumer-build", ["g++", "-std=c++17", ROOT / "tools/desktop/link_probe.cc", "-ldl", "-o", binary])
    if context.run("linked-consumer-run", [binary, payload / "runtime" / LIBRARY], output=True, env=platform_data.environment(payload)).strip() != b"SYNCWATCH_NATIVE_LINK_OK":
        raise ValueError("Original linked Skiko/Skia API consumer failed")
    return binary


def fault_checks(context, payload, binary):
    """Reject corrupted owned copies, then execute an untouched Unicode relocation."""
    import tempfile

    patchelf = shutil.which("patchelf", path=context.env["PATH"])
    if not patchelf:
        raise ValueError("Native negative checks require the declared patchelf SDK tool")
    failures = []
    with tempfile.TemporaryDirectory(prefix="native-errors-", dir=context.work) as temporary:
        root = Path(temporary)
        for name in FAULT_CASES[:-1]:
            directory = root / name
            shutil.copytree(payload / "runtime", directory)
            library = directory / LIBRARY
            if name == "missing-client":
                (directory / "libX11.so.6").unlink()
            elif name == "foreign-runpath":
                context.run(name + "-mutate", [patchelf, "--set-rpath", "/unowned/native", library])
            elif name == "foreign-import":
                context.run(name + "-mutate", [patchelf, "--add-needed", "libsyncwatch-unowned.so", library])
            elif name == "incompatible-elf":
                data = bytearray(library.read_bytes())
                data[18:20] = (183).to_bytes(2, "little")  # An incompatible AArch64 ELF e_machine.
                library.write_bytes(data)
            else:
                alias = directory / "libdbus-1.so"
                alias.unlink()
                alias.symlink_to("missing-library.so")
            try:
                audit(directory)
            except ValueError:
                failures.append(name)
            else:
                raise ValueError("Corrupt runtime was accepted: " + name)
        missing = root / "missing-locale-data"
        shutil.copytree(payload / "runtime", missing / "runtime")
        try:
            context.run("missing-locale-consumer", [binary, missing / "runtime" / LIBRARY], output=True,
                        env=platform_data.environment(missing))
        except ValueError:
            if b"SYNCWATCH_X11_LOCALE_UNAVAILABLE" not in (context.logs / "missing-locale-consumer.log").read_bytes():
                raise ValueError("Missing locale data failed for an unrelated reason")
            failures.append("missing-locale-data")
        else:
            raise ValueError("Runtime unexpectedly accepted absent owned locale data")
        relocated = root / "owned runtime with spaces — Кириллица"
        shutil.copytree(payload / "runtime", relocated / "runtime")
        shutil.copytree(payload / "share", relocated / "share")
        audit(relocated / "runtime")
        if context.run("relocated-linked-consumer", [binary, relocated / "runtime" / LIBRARY], output=True,
                       env=platform_data.environment(relocated)).strip() != b"SYNCWATCH_NATIVE_LINK_OK":
            raise ValueError("Linked runtime failed after Unicode/space relocation")
    return failures
