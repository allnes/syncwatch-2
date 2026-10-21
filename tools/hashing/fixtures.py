"""Validate frozen digest answers and generate a bounded C fixture, never crypto code."""

import json
from pathlib import Path


CHUNKS = [1, 7, 63, 136, 257]
LENGTHS = [16, 20, 28, 32, 48, 64, 28, 32, 48, 64, 192, 192]


def fixture_data(path, algorithms):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data["schemaVersion"] != 1 or data["algorithms"] != algorithms or data["shakeBytes"] != 192:
        raise ValueError("Unknown native hash answer profile")
    vectors = data["vectors"]
    if not isinstance(vectors, list) or not 2 <= len(vectors) <= 64:
        raise ValueError("Native hash fixture vector count exceeds bounds")
    result = []
    for vector in vectors:
        source = bytes.fromhex(vector["inputHex"])
        if len(source) > 4096:
            raise ValueError("Native hash fixture input exceeds bounds")
        answers = []
        for key in ["answers", "appended"]:
            if set(vector[key]) != set(algorithms):
                raise ValueError("Native hash answers have missing or unknown algorithms")
            values = [vector[key][name] for name in algorithms]
            if any(not isinstance(text, str) or len(text) != size * 2 or bytes.fromhex(text).hex() != text
                   for text, size in zip(values, LENGTHS)):
                raise ValueError("Native hash digest length or encoding differs")
            answers.append(values)
        result.append((source, answers))
    if result[0][0] != b"":
        raise ValueError("The first native hash fixture must be the empty input")
    return result


def header(path, algorithms):
    vectors = fixture_data(path, algorithms)
    lines = ["/* First-party frozen digest fixtures. */"]
    for index, (source, _answers) in enumerate(vectors):
        lines.append(f"static uint8_t input_{index}[] = {{" + ",".join(str(v) for v in source or b"\0") + "};")
    lines += ["static const char *algorithm_names[] = {" + ",".join(map(json.dumps, algorithms)) + "};",
              "typedef struct { uint8_t *input; uint32_t length; const char *answers[12]; const char *appended[12]; } vector;",
              "static const vector vectors[] = {"]
    for index, (source, answers) in enumerate(vectors):
        lines.append(f"{{input_{index}, {len(source)}, {{" + ",".join(map(json.dumps, answers[0])) + "}, {" + ",".join(map(json.dumps, answers[1])) + "}},")
    lines += ["};", "static const uint32_t chunks[] = {" + ",".join(map(str, CHUNKS)) + "};", ""]
    return "\n".join(lines).encode(), len(vectors)


def expected_report(count):
    return {"pointerBits": 64, "algorithms": 12, "vectors": count, "knownAnswers": count * 12,
            "streamingCases": count * 12 * len(CHUNKS), "chunkSizes": CHUNKS,
            "copyResetAppend": True, "repeatDigest": True, "zeroLengthUpdate": True}
