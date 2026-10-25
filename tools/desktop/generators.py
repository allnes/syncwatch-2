"""Evaluate the reviewed original GN, Fontconfig and D-Bus header templates."""

import re


def substitute(template, values):
    text = template.decode()
    markers = set(re.findall(r"@([A-Z0-9_]+)@", text))
    if markers != set(values):
        raise ValueError("Original native header template parameters changed")
    for key, value in values.items():
        text = text.replace("@" + key + "@", str(value))
    return text.encode()


def original_version(source):
    matches = re.findall(r"version\s*:\s*'([0-9]+\.[0-9]+\.[0-9]+)'", source.decode())
    if len(matches) != 1:
        raise ValueError("Review the original native library version declaration")
    return tuple(matches[0].split("."))


def headers(originals, profile):
    gn = originals["gn"]["build/gen.py"].decode()
    templates = re.findall(r"contents = '''(.*?)''' % \(mo.group", gn, re.S)
    if len(templates) != 1:
        raise ValueError("Original GN version generator changed")
    version = profile["gnVersion"]
    generated_gn = templates[0] % (version["commitPosition"], str(version["commitPosition"]), version["commitAbbreviation"])
    if version["commitAbbreviation"] != profile["sources"]["gn"]["revision"][:12]:
        raise ValueError("GN version does not describe the exact source revision")
    font = originals["fontconfig"]
    build = font["meson.build"].decode()
    values = {}
    for key in ("cacheversion", "cachemincompat", "cachesnapversion"):
        found = re.findall(r"^" + key + r" = ([0-9]+)$", build, re.M)
        if len(found) != 1:
            raise ValueError("Original Fontconfig cache declaration changed")
        values[key] = int(found[0])
    if "if cachesnapversion > 0\n  nextcacheversion = cacheversion + 1\nelse\n  nextcacheversion = 0\nendif" not in build:
        raise ValueError("Original Fontconfig next-cache generation changed")
    generated_font = substitute(font["fontconfig/fontconfig.h.in"], {
        "CACHE_VERSION": values["cacheversion"], "CACHE_MIN_COMPAT_VERSION": values["cachemincompat"],
        "CACHE_SNAP_VERSION": values["cachesnapversion"],
        "NEXT_CACHE_VERSION": values["cacheversion"] + 1 if values["cachesnapversion"] > 0 else 0})
    major, minor, micro = original_version(originals["desktop-dbus"]["meson.build"])
    generated_dbus = substitute(originals["desktop-dbus"]["dbus/dbus-arch-deps.h.in"], {
        "DBUS_INT64_TYPE": "long", "DBUS_INT64_MODIFIER": "l", "DBUS_INT64_CONSTANT": "(val##L)",
        "DBUS_UINT64_CONSTANT": "(val##UL)", "DBUS_INT32_TYPE": "int", "DBUS_INT16_TYPE": "short",
        "DBUS_SIZEOF_VOID_P": 8, "DBUS_MAJOR_VERSION": major, "DBUS_MINOR_VERSION": minor,
        "DBUS_MICRO_VERSION": micro, "DBUS_VERSION": ".".join((major, minor, micro))})
    return {"gn/last_commit_position.h": generated_gn,
            "fontconfig/fontconfig.h": generated_font,
            "fontconfig/fcfreetype.h": font["fontconfig/fcfreetype.h"],
            "dbus/dbus-arch-deps.h": generated_dbus}
