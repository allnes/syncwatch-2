/* First-party driver for exact original raw SipHash functions. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
#ifdef _MSC_VER
#include <intrin.h>
#endif
#include "fixture.h"
#include "corpus.h"

_Static_assert(CHAR_BIT == 8 && sizeof(unsigned int) == 4 && sizeof(Py_ssize_t) == 8 && sizeof(size_t) == 8,
               "SipHash transcript requires the declared 64-bit host configuration");

static uint64_t little64(const unsigned char *bytes)
{
    uint64_t value = 0;
    for (size_t i = 0; i < 8; ++i) value |= (uint64_t)bytes[i] << (i * 8);
    return value;
}

static void big64(unsigned char *out, uint64_t value)
{
    for (size_t i = 0; i < 8; ++i) out[i] = (unsigned char)(value >> ((7 - i) * 8));
}

static int record(const unsigned char *message, size_t length, size_t key, size_t offset)
{
    unsigned char buffer[sizeof(fixture_messages[0]) + FIXTURE_ALIGNMENTS];
    unsigned char result[24];
    const uint64_t k0 = little64(fixture_keys[key]);
    const uint64_t k1 = little64(fixture_keys[key] + 8);
    const void *input;
    memset(buffer, 0xa5, sizeof(buffer));
    memcpy(buffer + offset, message, length);
    input = length == 0 && offset == 0 ? NULL : buffer + offset;
    big64(result, siphash13(k0, k1, input, (Py_ssize_t)length));
    big64(result + 8, siphash24(k0, k1, input, (Py_ssize_t)length));
    big64(result + 16, _Py_KeyedHash(k0, input, (Py_ssize_t)length));
    return fwrite(result, 1, sizeof(result), stdout) == sizeof(result);
}

int main(void)
{
    const uint32_t endian = 1;
    unsigned char prefix[12] = {'S','W','S','I','P','0','1',0};
    uint32_t count = 0;
    if (*(const unsigned char *)&endian != 1) return 2;
#ifdef _WIN32
    if (_setmode(_fileno(stdout), _O_BINARY) == -1) return 3;
#endif
    prefix[8] = (unsigned char)(FIXTURE_CASES >> 24);
    prefix[9] = (unsigned char)(FIXTURE_CASES >> 16);
    prefix[10] = (unsigned char)(FIXTURE_CASES >> 8);
    prefix[11] = (unsigned char)FIXTURE_CASES;
    if (fwrite(prefix, 1, sizeof(prefix), stdout) != sizeof(prefix)) return 4;
    for (size_t key = 0; key < sizeof(fixture_keys) / sizeof(fixture_keys[0]); ++key)
        for (size_t pattern = 0; pattern < sizeof(fixture_messages) / sizeof(fixture_messages[0]); ++pattern)
            for (size_t n = 0; n < sizeof(fixture_lengths) / sizeof(fixture_lengths[0]); ++n)
                for (size_t offset = 0; offset < FIXTURE_ALIGNMENTS; ++offset) {
                    if (!record(fixture_messages[pattern], fixture_lengths[n], key, offset)) return 5;
                    ++count;
                }
    for (size_t n = 0; n < sizeof(fixture_known_keys) / sizeof(fixture_known_keys[0]); ++n)
        for (size_t offset = 0; offset < FIXTURE_ALIGNMENTS; ++offset) {
            if (!record(fixture_known_messages[n], fixture_known_lengths[n], fixture_known_keys[n], offset)) return 6;
            ++count;
        }
    return count == FIXTURE_CASES && fflush(stdout) == 0 ? 0 : 7;
}
