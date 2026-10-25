"""Build the original X11 clients shared by renderer and native video recipes."""

import re
import shutil

from native_libraries import meson


SHARED = ("--enable-shared", "--disable-static")
NO_SPECS = ("--disable-specs", "--without-xmlto", "--without-fop", "--without-xsltproc")


def autotools(context, sources, name, options=()):
    source = sources[name]
    match = re.search(r"AC_CONFIG_AUX_DIR\(\[?([^\]\)]+)", (source / "configure.ac").read_text())
    auxiliary = source / match.group(1) if match else source
    auxiliary.mkdir(exist_ok=True)
    for filename, path in context.auxiliary_files().items():
        shutil.copy2(path, auxiliary / filename)
    context.run(name + "-autoreconf", [context.env["AUTORECONF"], "-fiv"], cwd=source)
    build = context.work / (name + "-build")
    build.mkdir()
    context.run(name + "-configure", [str(source / "configure"), "--prefix=" + str(context.prefix),
                "--libdir=" + str(context.prefix / "lib"), *options], cwd=build)
    context.run(name + "-build", ["make", "-j4"], cwd=build)
    context.run(name + "-install", ["make", "install"], cwd=build)


def build(context, sources):
    context.env["PKG_CONFIG_LIBDIR"] = (str(context.prefix / "lib/pkgconfig") + ":"
                                         + str(context.prefix / "share/pkgconfig"))
    context.env["PKG_CONFIG_PATH"] = ""
    context.env["ACLOCAL_PATH"] = str(context.prefix / "share/aclocal") + ":" + context.env.get("ACLOCAL_PATH", "")
    autotools(context, sources, "desktop-xorg-macros")
    meson(context, sources, "desktop-xorgproto", [])
    autotools(context, sources, "desktop-xtrans", ["--disable-docs"])
    autotools(context, sources, "desktop-xcb-proto")
    meson(context, sources, "desktop-libxau", [])
    autotools(context, sources, "desktop-libxdmcp", [*SHARED, "--disable-docs", "--disable-unit-tests", *NO_SPECS[1:]])
    autotools(context, sources, "desktop-libxcb", [*SHARED, "--disable-devel-docs", "--without-doxygen"])
    for name in ("desktop-libx11", "desktop-libxext"):
        autotools(context, sources, name, [*SHARED, *NO_SPECS])
    for name in ("desktop-libxrender", "desktop-libxrandr"):
        autotools(context, sources, name, SHARED)
