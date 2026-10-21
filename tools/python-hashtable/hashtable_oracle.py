"""Bounded, explicit operations and an independent dictionary oracle."""

import struct

PROFILES = 4
KEYS = 256


def operations():
    result = [(0, key) for key in range(KEYS)]
    result += [(1, key) for key in range(KEYS)]
    result += [(2, key) for key in range(0, KEYS, 3)]
    state = 0x12345678
    for _ in range(1200):
        state = (1664525 * state + 1013904223) & 0xffffffff
        result.append(((state >> 16) % 3, (state >> 24) % KEYS))
    result += [(2, key) for key in range(KEYS)]
    result += [(0, key) for key in range(64)]
    result += [(3, 0), (3, 0)]
    result += [(0, key) for key in range(64)]
    return result


def corpus_header():
    rows = ",\n".join("    {%d, %d}" % pair for pair in operations())
    return ("#define FIXTURE_PROFILES %d\n#define FIXTURE_KEYS %d\n#define FIXTURE_OPS %d\n"
            "static const unsigned int fixture_ops[][2] = {\n%s\n};\n" %
            (PROFILES, KEYS, len(operations()), rows)).encode("ascii")


def transcript():
    import hashlib
    data = bytearray(b"SWHT0001")
    for mode in range(PROFILES):
        table = {}
        for opcode, key in operations():
            found = key in table
            value = table.get(key, 0)
            if opcode == 0:
                if not found:
                    table[key] = key + 1000 if key else 0
                found, value = True, table[key]
            elif opcode == 2:
                table.pop(key, None)
            elif opcode == 3:
                table.clear()
                found, value = False, 0
            data += struct.pack(">7I", mode, opcode, key, int(found), value, len(table), sum(table.values()))
    # Fresh process-local allocations fail at every allocation of a real grow/
    # shrink/clear run. The C fixture checks rollback, reuse and no leaks;
    # only the number of completed logical scenarios enters the transcript.
    data += b"FAILURE_SWEEP_OK\n"
    return {"schemaVersion": 1, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "profiles": PROFILES, "operationsPerProfile": len(operations()), "keys": KEYS,
            "records": PROFILES * len(operations()), "failureSweep": True}
