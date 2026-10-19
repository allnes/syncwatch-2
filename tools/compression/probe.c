#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "zlib.h"

#define REQUIRE(expression) do { if (!(expression)) { \
    fprintf(stderr, "Compression probe failed at line %d: %s\n", __LINE__, #expression); \
    return 1; } } while (0)

static unsigned char input[16384];
static unsigned char compressed[32768];
static unsigned char decoded[16384];

static int streaming(int window_bits, const unsigned char *dictionary, uInt dictionary_size) {
    z_stream encoder = {0};
    z_stream decoder = {0};
    uLong initial_input;
    int result;
    REQUIRE(deflateInit2(&encoder, Z_DEFAULT_COMPRESSION, Z_DEFLATED,
                         window_bits, 8, Z_DEFAULT_STRATEGY) == Z_OK);
    if (dictionary != NULL) REQUIRE(deflateSetDictionary(&encoder, dictionary, dictionary_size) == Z_OK);
    initial_input = encoder.total_in;
    encoder.next_in = input;
    encoder.avail_in = (uInt)sizeof(input);
    encoder.next_out = compressed;
    encoder.avail_out = (uInt)sizeof(compressed);
    REQUIRE(deflate(&encoder, Z_FINISH) == Z_STREAM_END);
    REQUIRE(encoder.total_in - initial_input == sizeof(input));
    REQUIRE(deflateEnd(&encoder) == Z_OK);
    REQUIRE(inflateInit2(&decoder, window_bits) == Z_OK);
    decoder.next_in = compressed;
    decoder.avail_in = (uInt)encoder.total_out;
    decoder.next_out = decoded;
    decoder.avail_out = (uInt)sizeof(decoded);
    result = inflate(&decoder, Z_FINISH);
    if (dictionary != NULL) {
        REQUIRE(result == Z_NEED_DICT);
        REQUIRE(inflateSetDictionary(&decoder, dictionary, dictionary_size) == Z_OK);
        result = inflate(&decoder, Z_FINISH);
    }
    REQUIRE(result == Z_STREAM_END);
    REQUIRE(decoder.total_out == sizeof(input));
    REQUIRE(memcmp(decoded, input, sizeof(input)) == 0);
    REQUIRE(inflateEnd(&decoder) == Z_OK);
    return 0;
}

int main(int argc, char **argv) {
    size_t i;
    uLongf compressed_size, decoded_size;
    gzFile file;
    int result;
    const unsigned char dictionary[] = "SyncWatch compression fixture dictionary";
    REQUIRE(argc == 3);
    REQUIRE(sizeof(void *) == 8);
    REQUIRE(strcmp(zlibVersion(), ZLIB_VERSION) == 0);
    REQUIRE(strcmp(zlibVersion(), argv[1]) == 0);
    for (i = 0; i < sizeof(input); ++i) input[i] = (unsigned char)((i * 37U) % 251U);

    compressed_size = (uLongf)sizeof(compressed);
    REQUIRE(compress2(compressed, &compressed_size, input, (uLong)sizeof(input), Z_BEST_COMPRESSION) == Z_OK);
    decoded_size = (uLongf)sizeof(decoded);
    REQUIRE(uncompress(decoded, &decoded_size, compressed, compressed_size) == Z_OK);
    REQUIRE(decoded_size == sizeof(input) && memcmp(input, decoded, sizeof(input)) == 0);
    decoded_size = 1;
    REQUIRE(uncompress(decoded, &decoded_size, compressed, compressed_size) == Z_BUF_ERROR);
    decoded_size = (uLongf)sizeof(decoded);
    result = uncompress(decoded, &decoded_size, compressed, compressed_size / 2);
    REQUIRE(result == Z_DATA_ERROR || result == Z_BUF_ERROR);
    compressed[compressed_size - 1] ^= 1;
    decoded_size = (uLongf)sizeof(decoded);
    REQUIRE(uncompress(decoded, &decoded_size, compressed, compressed_size) == Z_DATA_ERROR);
    REQUIRE(crc32(0, (const Bytef *)"123456789", 9) == 0xcbf43926UL);
    REQUIRE(adler32(1, (const Bytef *)"123456789", 9) == 0x091e01deUL);
    REQUIRE(streaming(-MAX_WBITS, NULL, 0) == 0);
    REQUIRE(streaming(MAX_WBITS + 16, NULL, 0) == 0);
    REQUIRE(streaming(MAX_WBITS, dictionary, (uInt)sizeof(dictionary)) == 0);

    file = gzopen(argv[2], "wb");
    REQUIRE(file != NULL);
    REQUIRE(gzwrite(file, input, (unsigned)sizeof(input)) == (int)sizeof(input));
    REQUIRE(gzclose(file) == Z_OK);
    file = gzopen(argv[2], "rb");
    REQUIRE(file != NULL);
    REQUIRE(gzread(file, decoded, (unsigned)sizeof(decoded)) == (int)sizeof(decoded));
    REQUIRE(memcmp(input, decoded, sizeof(input)) == 0);
    REQUIRE(gzread(file, decoded, 1) == 0 && gzeof(file));
    REQUIRE(gzclose(file) == Z_OK);
    REQUIRE(remove(argv[2]) == 0);
    printf("{\"version\":\"%s\",\"pointerBits\":%u,\"cases\":["
           "\"roundTrip\",\"outputBound\",\"truncated\",\"corruptChecksum\","
           "\"checksums\",\"rawDeflate\",\"gzipStream\",\"dictionary\",\"gzipFileCleanup\"]}\n",
           zlibVersion(), (unsigned)(sizeof(void *) * 8));
    return 0;
}
