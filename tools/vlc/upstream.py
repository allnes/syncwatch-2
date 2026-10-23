"""Configure and compile libVLC and only the selected upstream plugins."""

import json
from pathlib import Path

from build_context import shell_path
from configuration import vlc_files
from source_profile import selected_plugins
from source_files import digest


def build(context, sources, profile):
    source = sources["vlc"]
    build = context.work / "vlc-build"
    build.mkdir()
    original = {name: (source / name).read_bytes() for name in ["configure.ac", "lib/media_player.c", "modules/common.am"]}
    derivatives = vlc_files(original, profile)
    for name, data in derivatives.items():
        (source / name).write_bytes(data)
    auxiliaries = context.auxiliary_files()
    for name, helper_source in auxiliaries.items():
        # Normally copied by Automake. Debian's relocated SDK links these
        # helpers into /usr/share/misc, so select the complete SDK data directly.
        import shutil
        shutil.copy2(helper_source, source / "autotools" / name)
    (context.work / "configuration-derivatives.json").write_text(json.dumps({
        "vlc": {name: {"originalSha256": digest(original[name]) if name in original else None,
                       "configuredSha256": digest(data)} for name, data in derivatives.items()},
        "macosAvailability": "Upstream pipe/dup fallbacks selected for macOS13 compatibility",
        "gnuConfig": {name: str(path) for name, path in auxiliaries.items()}}, indent=2) + "\n", encoding="utf-8", newline="\n")
    context.run("vlc-bootstrap", ["./bootstrap"], cwd=source, shell=True)
    flags = ["--prefix=" + shell_path(context.prefix), "--disable-sout", "--disable-vlm",
        "--disable-lua", "--disable-qt", "--disable-skins2", "--disable-nls", "--disable-dbus",
        "--disable-postproc", "--disable-libva", "--disable-wayland", "--disable-xcb", "--disable-pulse",
        "--disable-gnutls", "--disable-smbclient", "--disable-libgcrypt", "--disable-notify",
        "--disable-macosx", "--disable-sparkle", "--disable-chromecast",
        "--enable-avcodec", "--enable-avformat", "--enable-swscale", "--enable-freetype",
        "--enable-fribidi", "--enable-harfbuzz", "--enable-libass", "--enable-samplerate"]
    if context.target == "windows-x64":
        flags.extend(["--with-libiconv-prefix=" + shell_path(context.prefix),
                      "--host=x86_64-w64-mingw32", "--build=x86_64-pc-msys"])
    else:
        flags.append("--without-libiconv-prefix")
    if context.target == "linux-x64":
        flags.append("--disable-alsa")
    # VLC 3 uses the C11 atomic initialization API, removed by C23. Modern GCC
    # defaults to C23; select the upstream language contract explicitly.
    context.run("vlc-configure", [shell_path(source / "configure"), *flags], cwd=build, shell=True,
                env={"CFLAGS": context.env["CFLAGS"] + " -std=gnu11"})
    for name in ["compat", "src", "lib"]:
        context.run("vlc-" + name, ["make", "-j4", "-C", name, "all"], cwd=build, shell=True)
    if context.target == "windows-x64":
        # Explicit plugin targets do not trigger Automake's BUILT_SOURCES rule.
        context.run("vlc-resources", ["make", "-C", "modules", "module.rc.lo"], cwd=build, shell=True)
    context.run("vlc-plugins", ["make", "-j4", "-C", "modules",
        *("lib" + name + "_plugin.la" for name in selected_plugins(profile, context.target))], cwd=build, shell=True)
    return build
