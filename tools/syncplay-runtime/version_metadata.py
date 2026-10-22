"""Bind upstream Versioneer's archive keywords to the pinned Git metadata."""

import json
import re


def constantly_version(source, authority):
    text = source["constantly/_version.py"].decode()
    values = {"git_refnames": "(tag: " + authority["version"] + ")",
              "git_full": authority["revision"], "git_date": authority["archiveDate"]}
    for name, value in values.items():
        text, count = re.subn(r"(?m)^    " + name + r' = "\$Format:[^"]+\$"$',
                              "    " + name + " = " + json.dumps(value), text)
        if count != 1:
            raise ValueError("Original Versioneer archive keyword differs")
    return ("# SyncWatch 2026-10-22: bind original Versioneer archive keywords to pinned Git metadata.\n" + text).encode()
