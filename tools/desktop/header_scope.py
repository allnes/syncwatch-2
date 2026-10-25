"""Reject application-library headers from ambient system/foreign SDK directories."""

from pathlib import Path
import shlex


C_HEADERS = set("""alloca.h assert.h byteswap.h complex.h cpio.h ctype.h dirent.h dlfcn.h elf.h endian.h errno.h
features.h features-time64.h fcntl.h fenv.h float.h fnmatch.h glob.h grp.h iconv.h inttypes.h langinfo.h
libgen.h libintl.h limits.h link.h locale.h malloc.h math.h mcheck.h memory.h mntent.h netdb.h nl_types.h
paths.h poll.h pthread.h pwd.h regex.h resolv.h sched.h search.h semaphore.h setjmp.h signal.h spawn.h
stdalign.h stdarg.h stdatomic.h stdbool.h stdc-predef.h stddef.h stdint.h stdio.h stdio_ext.h stdlib.h
string.h strings.h stropts.h syscall.h sysexits.h syslog.h tar.h termio.h termios.h tgmath.h threads.h
time.h uchar.h ucontext.h ulimit.h unistd.h utime.h utmp.h utmpx.h values.h wchar.h wctype.h xlocale.h""".split())
OS_FAMILIES = {"bits", "sys", "gnu", "asm", "asm-generic", "linux", "arpa", "net", "netinet", "netpacket", "protocols"}


def sdk_header(path, compiler_include, jdk_include):
    if path.is_relative_to(compiler_include) or path.is_relative_to(jdk_include):
        return True
    for root in (Path("/usr/include"), Path("/usr/include/x86_64-linux-gnu")):
        if path.is_relative_to(root):
            parts = path.relative_to(root).parts
            if parts and (parts[0] in OS_FAMILIES or parts[0] == "c++"):
                return True
            if len(parts) == 1 and parts[0] in C_HEADERS:
                return True
    return False


def verify(paths, original_paths, generated_roots, compiler_include, jdk_include):
    visited = set()
    for value in paths:
        if str(value) in visited:
            continue
        visited.add(str(value))
        path = Path(value).resolve()
        if path in original_paths or any(path.is_relative_to(root) for root in generated_roots):
            continue
        if not sdk_header(path, compiler_include, jdk_include):
            raise ValueError("Native compiler consumed an undeclared application header: " + str(path))
    return len(visited)


def ninja_paths(text, directory):
    return [directory / line.strip() for line in text.splitlines() if line.startswith("    ")]


def make_paths(text):
    return shlex.split(text.split(":", 1)[1].replace(chr(92) + chr(10), " "))
