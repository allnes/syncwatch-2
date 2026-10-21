"""Independent raw-source/table oracle; never uses the SDK Unicode database."""

from fractions import Fraction
import hashlib
import re
import struct

UCD = "unicodetools/data/ucd/15.0.0/"
TAGS = ("kAccountingNumeric", "kOtherNumeric", "kPrimaryNumeric")
LIMIT = 0x110000
GUARDS = (LIMIT, LIMIT + 1, 0xFFFFFFFF)
SIGNATURE = b"SWUCT01\0"


def numeric_rows(files):
    rows = []
    for tag in TAGS:
        for line in files[UCD + "Unihan/" + tag + ".txt"].decode("ascii").splitlines():
            match = re.fullmatch(r"([0-9A-F]{4,6})(?:\.\.([0-9A-F]{4,6}))?\t([0-9]+)", line)
            if not match:
                raise ValueError("Unexpected original Unihan numeric record")
            start, end, value = match.groups()
            first, last = int(start, 16), int(end or start, 16)
            if not 0 <= first <= last < LIMIT:
                raise ValueError("Invalid Unihan numeric range")
            rows.extend((cp, tag, value) for cp in range(first, last + 1))
    if len(rows) != len(set((cp, tag) for cp, tag, _ in rows)):
        raise ValueError("Duplicate Unihan numeric property")
    return sorted(rows)


def interchange(files):
    return "".join("U+%04X\t%s\t%s\n" % row for row in numeric_rows(files)).encode("ascii")


def properties(files):
    numeric, whitespace, linebreak = {}, set(), set()
    for line in files[UCD + "UnicodeData.txt"].decode("utf-8").splitlines():
        values = line.split(";")
        if len(values) != 15:
            raise ValueError("Unexpected UnicodeData record")
        cp = int(values[0], 16)
        if values[8]:
            numeric[cp] = float(Fraction(values[8]))
        if values[2] == "Zs" or values[4] in {"WS", "B", "S"}:
            whitespace.add(cp)
        if values[4] == "B":
            linebreak.add(cp)
    for cp, _tag, value in numeric_rows(files):
        numeric[cp] = float(Fraction(value))
    for line in files[UCD + "LineBreak.txt"].decode("utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        span, prop = (item.strip() for item in line.split(";"))
        if prop in {"BK", "CR", "LF", "NL"}:
            parts = span.split("..")
            linebreak.update(range(int(parts[0], 16), int(parts[-1], 16) + 1))
    return numeric, whitespace, linebreak


def tables(header):
    text = header.decode("ascii")
    def array(name):
        matches = re.findall(r"\b" + name + r"\[\] = \{(.*?)\n\};", text, re.S)
        if len(matches) != 1:
            raise ValueError("Missing or ambiguous Unicode table: " + name)
        return matches[0]
    records = [tuple(map(int, match)) for match in re.findall(
        r"\{(-?\d+), (-?\d+), (-?\d+), (\d+), (\d+), (\d+)\},", array("_PyUnicode_TypeRecords"))]
    def integers(name):
        body = array(name)
        if not re.fullmatch(r"[\d,\s]+", body):
            raise ValueError("Unexpected Unicode table initializer")
        return list(map(int, re.findall(r"\d+", body)))
    first, second, extended = (integers(name) for name in ("index1", "index2", "_PyUnicode_ExtendedCase"))
    shifts = re.findall(r"^#define SHIFT (\d+)$", text, re.M)
    if len(shifts) != 1 or not records:
        raise ValueError("Invalid Unicode type table")
    shift = int(shifts[0])
    if (shift != 7 or len(first) != LIMIT >> shift or max(first) << shift >= len(second)
            or len(second) % (1 << shift) or max(second) >= len(records)):
        raise ValueError("Unicode table index is out of bounds")
    return records, first, second, extended, shift


def transcript(header, files):
    records, first, second, extended, shift = tables(header)
    numeric, whitespace, linebreak = properties(files)
    result = hashlib.sha256()
    count = LIMIT + len(GUARDS)
    result.update(SIGNATURE + struct.pack(">I", count))
    for cp in range(count):
        cp = cp if cp < LIMIT else GUARDS[cp - LIMIT]
        row = records[second[(first[cp >> shift] << shift) + (cp & ((1 << shift) - 1))]] if cp < LIMIT else records[0]
        result.update(struct.pack(">6IdII", *(v & 0xFFFFFFFF for v in row), numeric.get(cp, -1.0),
                                  int(cp in whitespace), int(cp in linebreak)))
    result.update(struct.pack(">I", len(extended)))
    for value in extended:
        result.update(struct.pack(">I", value))
    return {"schemaVersion": 1, "sha256": result.hexdigest(), "bytes": 12 + count * 40 + 4 + len(extended) * 4,
            "codePointSlots": LIMIT, "rangeGuards": list(GUARDS), "typeRecords": len(records),
            "extendedCaseValues": len(extended), "numericCodePoints": len(numeric),
            "whitespaceCodePoints": len(whitespace), "linebreakCodePoints": len(linebreak)}
