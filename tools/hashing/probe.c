/* SPDX-License-Identifier: Apache-2.0 */
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include "syncwatch_hacl.h"
#include "vectors.h"

_Static_assert(sizeof(void *) * CHAR_BIT == 64, "The hash profile requires a 64-bit host");
#define COUNT(values) (sizeof(values) / sizeof((values)[0]))
#define VERIFY(value) do { if (!(value)) { fprintf(stderr, "Hash assertion at line %d\n", __LINE__); goto done; } } while (0)

typedef struct {
    const char *name;
    size_t length;
    void (*one)(uint8_t *, uint8_t *, uint32_t);
    void *(*make)(void);
    void *(*copy)(void *);
    void (*reset)(void *);
    int (*update)(void *, uint8_t *, uint32_t);
    int (*digest)(void *, uint8_t *);
    void (*release)(void *);
} hash_api;

#define ADAPTER(tag, make_fn, copy_fn, reset_fn, update_fn, digest_fn, free_fn) \
    static void *tag##_make(void) { return make_fn(); } \
    static void *tag##_copy(void *state) { return copy_fn(state); } \
    static void tag##_reset(void *state) { reset_fn(state); } \
    static int tag##_update(void *state, uint8_t *data, uint32_t length) { return update_fn(state, data, length) == Hacl_Streaming_Types_Success; } \
    static int tag##_digest(void *state, uint8_t *out) { digest_fn(state, out); return 1; } \
    static void tag##_release(void *state) { free_fn(state); }

ADAPTER(md5, Hacl_Hash_MD5_malloc, Hacl_Hash_MD5_copy, Hacl_Hash_MD5_reset, Hacl_Hash_MD5_update, Hacl_Hash_MD5_digest, Hacl_Hash_MD5_free)
ADAPTER(sha1, Hacl_Hash_SHA1_malloc, Hacl_Hash_SHA1_copy, Hacl_Hash_SHA1_reset, Hacl_Hash_SHA1_update, Hacl_Hash_SHA1_digest, Hacl_Hash_SHA1_free)
ADAPTER(sha224, Hacl_Hash_SHA2_malloc_224, Hacl_Hash_SHA2_copy_256, Hacl_Hash_SHA2_reset_224, Hacl_Hash_SHA2_update_224, Hacl_Hash_SHA2_digest_224, Hacl_Hash_SHA2_free_224)
ADAPTER(sha256, Hacl_Hash_SHA2_malloc_256, Hacl_Hash_SHA2_copy_256, Hacl_Hash_SHA2_reset_256, Hacl_Hash_SHA2_update_256, Hacl_Hash_SHA2_digest_256, Hacl_Hash_SHA2_free_256)
ADAPTER(sha384, Hacl_Hash_SHA2_malloc_384, Hacl_Hash_SHA2_copy_512, Hacl_Hash_SHA2_reset_384, Hacl_Hash_SHA2_update_384, Hacl_Hash_SHA2_digest_384, Hacl_Hash_SHA2_free_384)
ADAPTER(sha512, Hacl_Hash_SHA2_malloc_512, Hacl_Hash_SHA2_copy_512, Hacl_Hash_SHA2_reset_512, Hacl_Hash_SHA2_update_512, Hacl_Hash_SHA2_digest_512, Hacl_Hash_SHA2_free_512)

#define SHA3_ALLOC(tag, algorithm) static void *tag##_make(void) { return Hacl_Hash_SHA3_malloc(algorithm); }
SHA3_ALLOC(sha3_224, Spec_Hash_Definitions_SHA3_224)
SHA3_ALLOC(sha3_256, Spec_Hash_Definitions_SHA3_256)
SHA3_ALLOC(sha3_384, Spec_Hash_Definitions_SHA3_384)
SHA3_ALLOC(sha3_512, Spec_Hash_Definitions_SHA3_512)
SHA3_ALLOC(shake_128, Spec_Hash_Definitions_Shake128)
SHA3_ALLOC(shake_256, Spec_Hash_Definitions_Shake256)
static void *sha3_copy(void *state) { return Hacl_Hash_SHA3_copy(state); }
static void sha3_reset(void *state) { Hacl_Hash_SHA3_reset(state); }
static int sha3_update(void *state, uint8_t *data, uint32_t length) { return Hacl_Hash_SHA3_update(state, data, length) == Hacl_Streaming_Types_Success; }
static int sha3_digest(void *state, uint8_t *out) { return Hacl_Hash_SHA3_digest(state, out) == Hacl_Streaming_Types_Success; }
static int shake_digest(void *state, uint8_t *out) { return Hacl_Hash_SHA3_squeeze(state, out, 192) == Hacl_Streaming_Types_Success; }
static void sha3_release(void *state) { Hacl_Hash_SHA3_free(state); }
static void shake128_one(uint8_t *out, uint8_t *data, uint32_t length) { Hacl_Hash_SHA3_shake128_hacl(length, data, 192, out); }
static void shake256_one(uint8_t *out, uint8_t *data, uint32_t length) { Hacl_Hash_SHA3_shake256_hacl(length, data, 192, out); }

#define ENTRY(tag, width, one_fn) { #tag, width, one_fn, tag##_make, tag##_copy, tag##_reset, tag##_update, tag##_digest, tag##_release }
#define SHA3_ENTRY(tag, width, one_fn, digest_fn) { #tag, width, one_fn, tag##_make, sha3_copy, sha3_reset, sha3_update, digest_fn, sha3_release }
static const hash_api apis[] = {
    ENTRY(md5, 16, Hacl_Hash_MD5_hash), ENTRY(sha1, 20, Hacl_Hash_SHA1_hash),
    ENTRY(sha224, 28, Hacl_Hash_SHA2_hash_224), ENTRY(sha256, 32, Hacl_Hash_SHA2_hash_256),
    ENTRY(sha384, 48, Hacl_Hash_SHA2_hash_384), ENTRY(sha512, 64, Hacl_Hash_SHA2_hash_512),
    SHA3_ENTRY(sha3_224, 28, Hacl_Hash_SHA3_sha3_224, sha3_digest),
    SHA3_ENTRY(sha3_256, 32, Hacl_Hash_SHA3_sha3_256, sha3_digest),
    SHA3_ENTRY(sha3_384, 48, Hacl_Hash_SHA3_sha3_384, sha3_digest),
    SHA3_ENTRY(sha3_512, 64, Hacl_Hash_SHA3_sha3_512, sha3_digest),
    SHA3_ENTRY(shake_128, 192, shake128_one, shake_digest),
    SHA3_ENTRY(shake_256, 192, shake256_one, shake_digest)
};

static int matches(uint8_t *out, size_t length, const char *hex)
{
    static const char digits[] = "0123456789abcdef";
    size_t index;
    if (strlen(hex) != length * 2) return 0;
    for (index = 0; index < length; ++index) {
        if (digits[out[index] >> 4] != hex[index * 2] || digits[out[index] & 15] != hex[index * 2 + 1]) return 0;
    }
    for (; index < 256; ++index) if (out[index] != 0xa5) return 0;
    return 1;
}

static int digest_matches(const hash_api *api, void *state, const char *expected)
{
    uint8_t out[256];
    memset(out, 0xa5, sizeof(out));
    return api->digest(state, out) && matches(out, api->length, expected);
}

static int streaming(const hash_api *api, const vector *v, size_t algorithm, uint32_t chunk)
{
    void *state = api->make();
    void *copy = NULL;
    uint32_t offset = 0;
    uint8_t appended = 'Z';
    int success = 0;
    VERIFY(state != NULL);
    VERIFY(api->update(state, v->input, 0));
    while (offset < v->length) {
        uint32_t length = v->length - offset;
        if (length > chunk) length = chunk;
        VERIFY(api->update(state, v->input + offset, length));
        offset += length;
    }
    VERIFY(api->update(state, v->input, 0));
    VERIFY(digest_matches(api, state, v->answers[algorithm]));
    VERIFY(digest_matches(api, state, v->answers[algorithm]));
    copy = api->copy(state);
    VERIFY(copy != NULL);
    api->reset(state);
    VERIFY(digest_matches(api, state, vectors[0].answers[algorithm]));
    VERIFY(digest_matches(api, copy, v->answers[algorithm]));
    VERIFY(api->update(copy, &appended, 1));
    VERIFY(digest_matches(api, copy, v->appended[algorithm]));
    success = 1;
done:
    if (copy != NULL) api->release(copy);
    if (state != NULL) api->release(state);
    return success;
}

int main(void)
{
    size_t algorithm, index, chunk;
    uint8_t out[256];
    _Static_assert(COUNT(apis) == COUNT(algorithm_names), "Fixture API count differs");
    for (algorithm = 0; algorithm < COUNT(apis); ++algorithm) {
        const hash_api *api = apis + algorithm;
        if (strcmp(api->name, algorithm_names[algorithm]) != 0) return 1;
        for (index = 0; index < COUNT(vectors); ++index) {
            const vector *v = vectors + index;
            memset(out, 0xa5, sizeof(out));
            api->one(out, v->input, v->length);
            if (!matches(out, api->length, v->answers[algorithm])) return 1;
            for (chunk = 0; chunk < COUNT(chunks); ++chunk)
                if (!streaming(api, v, algorithm, chunks[chunk])) return 1;
        }
    }
    printf("{\"pointerBits\":64,\"algorithms\":%u,\"vectors\":%u,\"knownAnswers\":%u,\"streamingCases\":%u,"
           "\"chunkSizes\":[1,7,63,136,257],\"copyResetAppend\":true,\"repeatDigest\":true,\"zeroLengthUpdate\":true}\n",
           (unsigned)COUNT(apis), (unsigned)COUNT(vectors), (unsigned)(COUNT(apis) * COUNT(vectors)),
           (unsigned)(COUNT(apis) * COUNT(vectors) * COUNT(chunks)));
    return 0;
}
