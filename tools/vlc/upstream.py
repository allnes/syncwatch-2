"""Configure and compile libVLC and only the selected upstream plugins."""

import datetime
import json
from pathlib import Path

from build_context import shell_path
from source_profile import selected_plugins


def build(context, sources, profile):
    source = sources["vlc"]
    build = context.work / "vlc-build"
    build.mkdir()
    # git archive omits repository metadata. Supply the precise original revision
    # and commit date as declared configuration derivatives, never a wall clock.
    (source / "src/revision.txt").write_bytes((profile["sources"]["vlc"]["revision"] + "\n").encode())
    configure = source / "configure.ac"
    text = configure.read_text()
    start = text.index("VERSION_DATE=$(")
    end = text.index("\n)", start) + 2
    original_fragment = text[start:end]
    date = datetime.datetime.fromtimestamp(profile["sourceDateEpoch"], datetime.timezone.utc).strftime("%Y-%m-%d")
    text = text[:start] + "dnl SyncWatch: deterministic date of the pinned original source commit.\nVERSION_DATE='" + date + "'" + text[end:]
    configure.write_bytes(text.encode())
    auxiliaries = context.auxiliary_files()
    for name, helper_source in auxiliaries.items():
        # Normally copied by Automake. Debian's relocated SDK links these
        # helpers into /usr/share/misc, so select the complete SDK data directly.
        import shutil
        shutil.copy2(helper_source, source / "autotools" / name)
    (context.work / "configuration-derivatives.json").write_text(json.dumps({
        "vlc/src/revision.txt": "Exact pinned original revision plus LF",
        "vlc/configure.ac": {"original": original_fragment, "configuredVersionDate": date},
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
    context.run("vlc-configure", [shell_path(source / "configure"), *flags], cwd=build, shell=True)
    for name in ["compat", "src", "lib"]:
        context.run("vlc-" + name, ["make", "-j4", "-C", name, "all"], cwd=build, shell=True)
    context.run("vlc-plugins", ["make", "-j4", "-C", "modules",
        *("lib" + name + "_plugin.la" for name in selected_plugins(profile, context.target))], cwd=build, shell=True)
    return build
