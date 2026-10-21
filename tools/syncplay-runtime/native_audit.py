"""Allow only owned runtime libraries and explicitly selected OS/SDK imports."""

from pathlib import Path
import re
import subprocess


def audit(files, target, sdk, options):
    owned = {p.name for p in files}
    records = {}
    for path in files:
        if target == "macos-arm64":
            command = ["otool", "-L", str(path)]
            allowed = {"@rpath/" + n for n in owned} | {"/usr/lib/libSystem.B.dylib", "/usr/lib/libobjc.A.dylib",
                "/usr/lib/libc++.1.dylib", "/usr/lib/libiconv.2.dylib",
                "/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation",
                "/System/Library/Frameworks/SystemConfiguration.framework/Versions/A/SystemConfiguration"}
        elif target == "linux-x64":
            command = ["readelf", "-d", str(path)]
            allowed = owned | {"libc.so.6", "libm.so.6", "libdl.so.2", "libpthread.so.0", "libutil.so.1",
                "libgcc_s.so.1", "librt.so.1", "ld-linux-x86-64.so.2"}
        else:
            instance = next(v.split("=", 1)[1] for v in options if v.startswith("-DCMAKE_GENERATOR_INSTANCE="))
            dumpbin = Path(instance) / "VC/Tools/MSVC" / sdk["compiler"].split()[1] / "bin/Hostx64/x64/dumpbin.exe"
            command = [str(dumpbin), "/nologo", "/dependents", str(path)]
            allowed = {n.upper() for n in owned} | {"KERNEL32.DLL", "KERNELBASE.DLL", "NTDLL.DLL", "ADVAPI32.DLL",
                "WS2_32.DLL", "MSWSOCK.DLL", "SHELL32.DLL", "USER32.DLL", "USERENV.DLL", "VERSION.DLL",
                "OLE32.DLL", "OLEAUT32.DLL", "BCRYPT.DLL", "BCRYPTPRIMITIVES.DLL", "CRYPT32.DLL", "NCRYPT.DLL",
                "SECUR32.DLL", "NORMALIZ.DLL", "UCRTBASE.DLL", "PATHCCH.DLL", "IPHLPAPI.DLL", "RPCRT4.DLL",
                "VCRUNTIME140.DLL", "VCRUNTIME140_1.DLL", "MSVCP140.DLL"}
        output = subprocess.check_output(command, text=True, stderr=subprocess.STDOUT, timeout=30)
        if target == "macos-arm64":
            dependencies = re.findall(r"^\s+(\S+) \(compatibility version", output, re.M)
        elif target == "linux-x64":
            dependencies = re.findall(r"\(NEEDED\).*\[([^\]]+)\]", output)
        else:
            dependencies = [n.upper() for n in re.findall(r"^\s+([A-Za-z0-9_.-]+\.dll)\s*$", output, re.M | re.I)]
        if not dependencies or any(n not in allowed and not (target == "windows-x64"
            and re.fullmatch(r"API-MS-WIN-(?:CRT|CORE|SECURITY)-[A-Z0-9-]+\.DLL", n)) for n in dependencies):
            raise ValueError("Runtime links an undeclared library: " + path.name + " " + repr(dependencies))
        records[path.name] = sorted(dependencies)
    return records
