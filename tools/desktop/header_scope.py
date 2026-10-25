"""Reject application-library headers from ambient system/foreign SDK directories."""

from pathlib import Path
import shlex
import subprocess


C_HEADERS = set("""alloca.h assert.h byteswap.h complex.h cpio.h ctype.h dirent.h dlfcn.h elf.h endian.h errno.h
features.h features-time64.h execinfo.h fcntl.h fenv.h float.h fnmatch.h glob.h grp.h iconv.h inttypes.h langinfo.h
getopt.h libgen.h libintl.h limits.h link.h locale.h malloc.h math.h mcheck.h memory.h mntent.h netdb.h nl_types.h
paths.h poll.h pthread.h pwd.h regex.h resolv.h sched.h search.h semaphore.h setjmp.h signal.h spawn.h
stdalign.h stdarg.h stdatomic.h stdbool.h stdc-predef.h stddef.h stdint.h stdio.h stdio_ext.h stdlib.h
string.h strings.h stropts.h syscall.h sysexits.h syslog.h tar.h termio.h termios.h tgmath.h threads.h
time.h uchar.h ucontext.h ulimit.h unistd.h utime.h utmp.h utmpx.h values.h wchar.h wctype.h xlocale.h""".split())
OS_FAMILIES = {"bits", "sys", "gnu", "asm", "asm-generic", "linux", "arpa", "net", "netinet", "netpacket", "protocols"}


def sdk_header(path, compiler_include, jdk_include, sdk_files=()):
    if path in sdk_files:
        return True
    if path.is_relative_to(compiler_include) or path.is_relative_to(jdk_include):
        return True
    for root in (Path("/usr/include"), Path("/usr/include/x86_64-linux-gnu")):
        if path.is_relative_to(root):
            parts = path.relative_to(root).parts
            if path.relative_to(root).as_posix() == "rpc/netdb.h":
                return True
            if parts and (parts[0] in OS_FAMILIES or parts[0] == "c++"):
                return True
            if len(parts) == 1 and parts[0] in C_HEADERS:
                return True
    return False


def verify(paths, original_paths, generated_roots, compiler_include, jdk_include, sdk_files=()):
    visited = set()
    for value in paths:
        if str(value) in visited:
            continue
        visited.add(str(value))
        path = Path(value).resolve()
        if path in original_paths or any(path.is_relative_to(root) for root in generated_roots):
            continue
        if not sdk_header(path, compiler_include, jdk_include, sdk_files):
            raise ValueError("Native compiler consumed an undeclared application header: " + str(path))
    return len(visited)


def ninja_paths(text, directory):
    return [directory / line.strip() for line in text.splitlines() if line.startswith("    ")]


def make_paths(text):
    # Automake -MP adds phony header rules after the first logical dependency rule.
    lines = text.replace(chr(92) + chr(10), " ").splitlines()
    if not lines or lines[0].lstrip().startswith("#"):
        return []
    logical = lines[0]
    if ":" not in logical:
        raise ValueError("Malformed native compiler dependency rule")
    return shlex.split(logical.split(":", 1)[1])


def clients(context, sources):
    paths, generated = [], [context.prefix.resolve()]
    for build in sorted(context.work.glob("*-build")):
        generated.append(build.resolve())
        if (build / "build.ninja").exists():
            text = subprocess.check_output(["ninja", "-C", str(build), "-t", "deps"], env=context.env, text=True)
            (context.logs / (build.name + "-header-dependencies.log")).write_text(text)
            paths.extend(ninja_paths(text, build))
        for depfile in sorted(build.rglob(".deps/*")):
            if depfile.is_file() and depfile.suffix in {".Po", ".Plo"}:
                paths.extend(depfile.parent.parent / path for path in make_paths(depfile.read_text()))
    if not paths:
        raise ValueError("Platform clients retained no compiler header dependencies")
    originals = {p.resolve() for source in sources.values() for p in source.rglob("*") if p.is_file()}
    compiler = Path(subprocess.check_output([context.env["CC"], "-print-file-name=include"], env=context.env, text=True).strip()).resolve()
    # Ninja can retain linker dependency files too. Permit only named C/compiler ABI inputs,
    # resolved by the declared compiler; never exempt a whole system library directory.
    sdk_files = set()
    for name in ("crtbeginS.o", "crtendS.o", "crti.o", "crtn.o", "libgcc.a", "libgcc_s.so", "libgcc_s.so.1",
                 "libc.so", "libc.so.6", "libc_nonshared.a", "libm.so", "libm.so.6", "libmvec.so.1", "ld-linux-x86-64.so.2"):
        value = subprocess.check_output([context.env["CC"], "-print-file-name=" + name], env=context.env, text=True).strip()
        path = Path(value)
        if not path.is_absolute() or not path.is_file():
            raise ValueError("Compiler cannot identify a required C ABI SDK input: " + name)
        sdk_files.add(path.resolve())
    return verify(paths, originals, generated, compiler, Path("/no-platform-jni-sdk"), sdk_files)
