"""Independent integer model, original known answers and bounded public fixture corpus."""

import ast
import hashlib
import re
import struct

MASK = (1 << 64) - 1
SIGNATURE = b"SWSIP01\0"
LENGTHS = tuple(range(256)) + (511, 512, 513, 1023, 1024, 1025, 4095, 4096, 4097)
ALIGNMENTS = 8


def seeded_key(seed):
    # Original CPython test-seed LCG; public deterministic fixtures, never runtime entropy.
    if seed == 0:
        return bytes(16)
    output = bytearray()
    for _ in range(16):
        seed = (seed * 214013 + 2531011) & 0xFFFFFFFF
        output.append((seed >> 16) & 255)
    return bytes(output)


KEYS = (bytes(range(16)), seeded_key(0), seeded_key(42), bytes([255]) * 16,
        bytes.fromhex("80018001800180018001800180018001"), bytes.fromhex("0123456789abcdeffedcba9876543210"))


def siphash(message, key, compression, finalization):
    if len(key) != 16 or (compression, finalization) not in {(1, 3), (2, 4)}:
        raise ValueError("Unsupported SipHash model parameters")
    k0, k1 = struct.unpack("<QQ", key)
    state = [k0 ^ 0x736F6D6570736575, k1 ^ 0x646F72616E646F6D,
             k0 ^ 0x6C7967656E657261, k1 ^ 0x7465646279746573]
    def rotate(value, bits):
        return ((value << bits) | (value >> (64 - bits))) & MASK
    def rounds(count):
        for _ in range(count):
            state[0] = (state[0] + state[1]) & MASK
            state[1] = rotate(state[1], 13) ^ state[0]
            state[0] = rotate(state[0], 32)
            state[2] = (state[2] + state[3]) & MASK
            state[3] = rotate(state[3], 16) ^ state[2]
            state[0] = (state[0] + state[3]) & MASK
            state[3] = rotate(state[3], 21) ^ state[0]
            state[2] = (state[2] + state[1]) & MASK
            state[1] = rotate(state[1], 17) ^ state[2]
            state[2] = rotate(state[2], 32)
    whole = len(message) // 8 * 8
    for offset in range(0, whole, 8):
        word = int.from_bytes(message[offset:offset + 8], "little")
        state[3] ^= word
        rounds(compression)
        state[0] ^= word
    last = ((len(message) & 255) << 56) | int.from_bytes(message[whole:], "little")
    state[3] ^= last
    rounds(compression)
    state[0] ^= last
    state[2] ^= 255
    rounds(finalization)
    return state[0] ^ state[1] ^ state[2] ^ state[3]


def source_answers(sources):
    match = re.findall(rb"uint64_t vectors\[64\] = \{(.*?)\n\};", sources["csiphash"]["test.c"], re.S)
    if len(match) != 1:
        raise ValueError("Missing or ambiguous original SipHash vectors")
    values = [int(v, 16) for v in re.findall(rb"0x([0-9a-f]{16})LLU", match[0])]
    if len(values) != 64:
        raise ValueError("Original SipHash corpus must contain 64 known answers")
    tree = ast.parse(sources["cpython"]["Lib/test/test_hash.py"])
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "StringlikeHashRandomizationTests")
    assignments = [n.value for n in node.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "known_hashes" for t in n.targets)]
    if len(assignments) != 1:
        raise ValueError("Missing or ambiguous original CPython known answers")
    known = ast.literal_eval(assignments[0])
    text = bytes.fromhex("e400fa0011220721")  # Original BMP fixture in 16-bit little-endian storage.
    cases = ((1, b"abc"), (2, b"abc"), (2, b"abcdefghijk"), (1, text), (2, text))
    answers = {name: [row[1] & MASK for row in known[name]] for name in ("siphash13", "siphash24")}
    if any(len(rows) != len(cases) for rows in answers.values()):
        raise ValueError("Unexpected CPython seeded known-answer shape")
    for length, expected in enumerate(values):
        if siphash(bytes(range(length)), KEYS[0], 2, 4) != expected:
            raise ValueError("Independent model differs from original SipHash24 known answers")
    for index, (key, message) in enumerate(cases):
        for name, rounds in (("siphash13", (1, 3)), ("siphash24", (2, 4))):
            if siphash(message, KEYS[key], *rounds) != answers[name][index]:
                raise ValueError("Independent model differs from original CPython known answers")
    return cases, {"siphash24": values, "cpython": answers}


def patterns():
    return (bytes(i & 255 for i in range(max(LENGTHS))),
            bytes((i * 131 + (i >> 8) + 17) & 255 for i in range(max(LENGTHS))))


def transcript(sources):
    cases, _answers = source_answers(sources)
    count = (len(KEYS) * len(patterns()) * len(LENGTHS) + len(cases)) * ALIGNMENTS
    output = hashlib.sha256(SIGNATURE + struct.pack(">I", count))
    def add(message, key):
        values = (siphash(message, key, 1, 3), siphash(message, key, 2, 4),
                  siphash(message, key[:8] + bytes(8), 1, 3))
        record = struct.pack(">QQQ", *values)
        for _ in range(ALIGNMENTS):
            output.update(record)
    for key in KEYS:
        for pattern in patterns():
            for length in LENGTHS:
                add(pattern[:length], key)
    for key, message in cases:
        add(message, KEYS[key])
    return {"schemaVersion": 1, "sha256": output.hexdigest(), "bytes": 12 + count * 24,
            "cases": count, "knownAnswers": count * 3, "algorithms": ["siphash13", "siphash24", "_Py_KeyedHash"],
            "fixtureKeys": len(KEYS), "messagePatterns": 2, "lengths": len(LENGTHS), "maximumLength": max(LENGTHS),
            "alignmentOffsets": ALIGNMENTS, "originalSipHash24Vectors": 64, "originalCPythonVectors": len(cases) * 2,
            "zeroLengthNullInput": True}


def corpus_header(sources):
    cases, _answers = source_answers(sources)
    lines = ["/* First-party public fixture bytes; original known-answer data stays in sources.zip. */"]
    def array(name, ctype, data):
        if isinstance(data[0], (bytes, tuple)):
            width = max(map(len, data))
            rows = ["{" + ",".join(str(v) for v in row) + "}" for row in data]
            lines.append("static const %s %s[%d][%d] = {%s};" % (ctype, name, len(data), width, ",".join(rows)))
        else:
            lines.append("static const %s %s[] = {%s};" % (ctype, name, ",".join(map(str, data))))
    array("fixture_keys", "unsigned char", KEYS)
    array("fixture_messages", "unsigned char", patterns())
    array("fixture_lengths", "size_t", LENGTHS)
    array("fixture_known_messages", "unsigned char", tuple(message for _, message in cases))
    array("fixture_known_keys", "size_t", tuple(key for key, _ in cases))
    array("fixture_known_lengths", "size_t", tuple(len(message) for _, message in cases))
    lines.extend(("#define FIXTURE_ALIGNMENTS " + str(ALIGNMENTS), "#define FIXTURE_CASES " + str((len(KEYS) * 2 * len(LENGTHS) + len(cases)) * ALIGNMENTS)))
    return ("\n".join(lines) + "\n").encode("ascii")
