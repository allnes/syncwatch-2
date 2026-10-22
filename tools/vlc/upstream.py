"""Configure and compile libVLC and only the selected upstream plugins."""

import datetime
import json
from pathlib import Path

from build_context import shell_path


def build(context, sources, profile):
    source = sources["vlc"]
    build = context.work / "vlc-build"
    build.mkdir()
    # git archive omits repository metadata. Supply the precise original revision
    # and commit date as declared configuration derivatives, never a wall clock.
    (source / "src/revision.txt").write_text(profile["sources"]["vlc"]["revision"] + "\n")
    configure = source / "configure.ac"
    text = configure.read_text()
    start = text.index("VERSION_DATE=$(")
    end = text.index("\n)", start) + 2
    original = text[start:end]
    date = datetime.datetime.fromtimestamp(profile["sourceDateEpoch"], datetime.timezone.utc).strftime("%Y-%m-%d")
    text = text[:start] + "dnl SyncWatch: deterministic date of the pinned original source commit.\nVERSION_DATE='" + date + "'" + text[end:]
    configure.write_text(text)
    (context.work / "configuration-derivatives.json").write_text(json.dumps({
        "vlc/src/revision.txt": "Exact pinned original revision plus LF",
        "vlc/configure.ac": {"original": original, "configuredVersionDate": date},
        "macosAvailability": "Upstream pipe/dup fallbacks selected for macOS13 compatibility"}, indent=2) + "\n")
    context.run("vlc-bootstrap", ["./bootstrap"], cwd=source, shell=True)
    flags = ["--prefix=" + shell_path(context.prefix), "--disable-sout", "--disable-vlm",
        "--disable-lua", "--disable-qt", "--disable-skins2", "--disable-nls", "--disable-dbus",
        "--disable-postproc", "--disable-libva", "--disable-wayland", "--disable-xcb", "--disable-pulse",
        "--disable-gnutls", "--disable-smbclient", "--disable-libgcrypt", "--disable-notify",
        "--disable-macosx", "--disable-sparkle", "--disable-chromecast",
        "--enable-avcodec", "--enable-avformat", "--enable-swscale", "--enable-freetype",
        "--enable-fribidi", "--enable-harfbuzz", "--enable-libass"]
    if context.target == "windows-x64":
        flags.append("--with-libiconv-prefix=" + shell_path(context.prefix))
    else:
        flags.append("--without-libiconv-prefix")
    context.run("vlc-configure", [shell_path(source / "configure"), *flags], cwd=build, shell=True)
    for name in ["compat", "src", "lib"]:
        context.run("vlc-" + name, ["make", "-j4", "-C", name, "all"], cwd=build, shell=True)
    context.run("vlc-plugins", ["make", "-j4", "-C", "modules",
        *("lib" + name + "_plugin.la" for name in profile["plugins"])], cwd=build, shell=True)
    return build
