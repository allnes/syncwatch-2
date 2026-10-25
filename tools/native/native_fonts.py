"""Relocate the pinned Fontconfig defaults without substituting OS font files."""

import ast
import re


def default_files(original):
    configuration = original["conf.d/meson.build"].decode()
    options = original["meson.options"].decode()
    files = ast.literal_eval(re.search(r"^conf_links = (\[.*?\])", configuration, re.M | re.S)[1])
    def option(name):
        block = re.search(r"option\('" + re.escape(name) + r"',(.*?)\)", options, re.S)[1]
        return re.search(r"value:\s*'([^']+)'", block)[1]
    hinting, subpixel = option("default-hinting"), option("default-sub-pixel-rendering")
    if hinting != "noinstall":
        files.append("10-hinting-" + hinting + ".conf")
    if subpixel != "noinstall":
        files.append("10-sub-pixel-" + subpixel + ".conf")
    bitmap = ast.literal_eval(re.search(r"bitmap_conf_options = (\{.*?\})", configuration, re.S)[1])
    if option("bitmap-conf") != "noinstall":
        files.append("70-" + bitmap[option("bitmap-conf")] + ".conf")
    return sorted(set(files))


def contents(original, profile):
    selected = default_files(original)
    if profile["fontconfigDefaults"] != selected:
        raise ValueError("Declared Fontconfig defaults differ from the pinned upstream configuration")
    result = {"share/fonts/conf.d/" + name: original["conf.d/" + name] for name in selected}
    template = original["fonts.conf.in"]
    values = {b"@FC_DEFAULT_FONTS@": b"<dir>/usr/share/fonts</dir>",
              b"@FC_FONTPATH@": b"<dir>/usr/local/share/fonts</dir>",
              b"@CONFIGDIR@": b"conf.d", b"@FC_CACHEDIR@": b"/var/cache/fontconfig"}
    for name, value in values.items():
        if template.count(name) != 1:
            raise ValueError("Review the upstream Fontconfig relocation template")
        template = template.replace(name, value)
    if re.search(rb"@[A-Z0-9_]+@", template):
        raise ValueError("Unconfigured Fontconfig template field")
    template = template.replace(b"<fontconfig>",
        b"<!-- SyncWatch modified 2026-10-23: owned relative configuration; OS/user fonts. -->\n<fontconfig>", 1)
    result["share/fonts/fonts.conf"] = template
    result["share/fonts/fonts.dtd"] = original["fonts.dtd"]
    return result
