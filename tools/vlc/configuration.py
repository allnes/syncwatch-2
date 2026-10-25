"""Explicit, narrowly scoped derivatives of the pinned original VLC sources."""

import datetime
import re


def pulse_version(original, profile):
    version = profile["linuxOutputScope"]["pulseVersion"]
    if (not re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", version)
            or original["NEWS"].splitlines()[0] != ("PulseAudio " + version).encode()
            or b"'.tarball-version'" not in original["meson.build"]
            or b".tarball-version" not in original["git-version-gen"]):
        raise ValueError("Review original PulseAudio distribution-version metadata")
    # This is the original release-tarball input, absent from a Git snapshot.
    # Do not let git-version-gen invent a version from the enclosing checkout.
    return (version + "\n").encode()


def vlc_files(original, profile):
    configure = original["configure.ac"].decode()
    start = configure.index("VERSION_DATE=$(")
    end = configure.index("\n)", start) + 2
    date = datetime.datetime.fromtimestamp(profile["sourceDateEpoch"], datetime.timezone.utc).strftime("%Y-%m-%d")
    configure = configure[:start] + "dnl SyncWatch modified 2026-10-23: deterministic original source commit date.\nVERSION_DATE='" + date + "'" + configure[end:]
    player = original["lib/media_player.c"]
    old = b'    var_Create (mp, "audio-filter", VLC_VAR_STRING);'
    if player.count(old) != 1:
        raise ValueError("Review the pinned VLC audio-filter initialization before applying its configuration derivative")
    player = player.replace(old, b'    /* SyncWatch modified 2026-10-23: inherit explicitly configured player filters. */\n'
                            b'    var_Create (mp, "audio-filter", VLC_VAR_STRING | VLC_VAR_DOINHERIT);')
    plugins = original["modules/common.am"]
    old = b'AM_LDFLAGS += $(top_builddir)/modules/module.rc.lo -Wc,-static'
    if plugins.count(old) != 1:
        raise ValueError("Review the pinned Windows plugin linker profile before configuring shared codecs")
    plugins = plugins.replace(old,
        b'# SyncWatch modified 2026-10-23: shared owned codecs, static compiler support.\n'
        b'AM_LDFLAGS += $(top_builddir)/modules/module.rc.lo -Wc,-static-libgcc -Wc,-static-libstdc++')
    return {"configure.ac": configure.encode(), "lib/media_player.c": player, "modules/common.am": plugins,
            "src/revision.txt": (profile["sources"]["vlc"]["revision"] + "\n").encode()}
