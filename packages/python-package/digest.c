/* SPDX-License-Identifier: Apache-2.0 */
#include <string.h>
#include "internal.h"

void swp_hash_init(swp_hash *hash)
{
    /* The upstream constructor initializes these same state/buffer pointers.
     * Caller-owned bounded storage avoids its unchecked allocation path. */
    memset(hash, 0, sizeof(*hash));
    hash->state.block_state = hash->words;
    hash->state.buf = hash->buffer;
    Hacl_Hash_SHA2_reset_256(&hash->state);
}
int swp_hash_update(swp_hash *hash, unsigned char *data, uint32_t size)
{
    return Hacl_Hash_SHA2_update_256(&hash->state, data, size) == Hacl_Streaming_Types_Success;
}
int swp_hash_matches(swp_hash *hash, const unsigned char expected[32])
{
    unsigned char digest[32];
    Hacl_Hash_SHA2_digest_256(&hash->state, digest);
    return memcmp(digest, expected, sizeof(digest)) == 0;
}
