/* First-party transcript driver; original source fragments live in fixture.h. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
#include <float.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
#include "fixture.h"

_Static_assert(CHAR_BIT == 8 && sizeof(int) == 4 && sizeof(Py_UCS4) == 4,
               "Unicode transcript requires 8-bit bytes and 32-bit native integers");
_Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53 && DBL_MAX_EXP == 1024,
               "Unicode transcript requires IEEE binary64");

static void big32(unsigned char *out, uint32_t value)
{
    out[0] = (unsigned char)(value >> 24);
    out[1] = (unsigned char)(value >> 16);
    out[2] = (unsigned char)(value >> 8);
    out[3] = (unsigned char)value;
}

static int record(Py_UCS4 cp)
{
    const _PyUnicode_TypeRecord *type = gettyperecord(cp);
    unsigned char bytes[40];
    double number = _PyUnicode_ToNumeric(cp);
    uint64_t bits;
    memcpy(&bits, &number, sizeof(bits));
    big32(bytes, (uint32_t)type->upper);
    big32(bytes + 4, (uint32_t)type->lower);
    big32(bytes + 8, (uint32_t)type->title);
    big32(bytes + 12, type->decimal);
    big32(bytes + 16, type->digit);
    big32(bytes + 20, type->flags);
    big32(bytes + 24, (uint32_t)(bits >> 32));
    big32(bytes + 28, (uint32_t)bits);
    big32(bytes + 32, (uint32_t)_PyUnicode_IsWhitespace(cp));
    big32(bytes + 36, (uint32_t)_PyUnicode_IsLinebreak(cp));
    return fwrite(bytes, 1, sizeof(bytes), stdout) == sizeof(bytes);
}

int main(void)
{
    unsigned char prefix[12] = {'S','W','U','C','T','0','1',0};
    unsigned char bytes[4];
    size_t i;
    const Py_UCS4 guards[] = {0x110000, 0x110001, UINT32_MAX};
    const double one = 1.0;
    uint64_t one_bits;
    memcpy(&one_bits, &one, sizeof(one_bits));
    if (one_bits != UINT64_C(0x3ff0000000000000)) return 2;
#ifdef _WIN32
    if (_setmode(_fileno(stdout), _O_BINARY) == -1) return 3;
#endif
    big32(prefix + 8, 0x110003);
    if (fwrite(prefix, 1, sizeof(prefix), stdout) != sizeof(prefix)) return 4;
    for (Py_UCS4 cp = 0; cp < 0x110000; ++cp) if (!record(cp)) return 5;
    for (i = 0; i < sizeof(guards) / sizeof(guards[0]); ++i) if (!record(guards[i])) return 6;
    big32(bytes, (uint32_t)(sizeof(_PyUnicode_ExtendedCase) / sizeof(_PyUnicode_ExtendedCase[0])));
    if (fwrite(bytes, 1, sizeof(bytes), stdout) != sizeof(bytes)) return 7;
    for (i = 0; i < sizeof(_PyUnicode_ExtendedCase) / sizeof(_PyUnicode_ExtendedCase[0]); ++i) {
        big32(bytes, _PyUnicode_ExtendedCase[i]);
        if (fwrite(bytes, 1, sizeof(bytes), stdout) != sizeof(bytes)) return 8;
    }
    return fflush(stdout) == 0 ? 0 : 9;
}
