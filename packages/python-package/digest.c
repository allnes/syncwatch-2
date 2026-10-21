/* SPDX-License-Identifier: Apache-2.0 */
#include <string.h>
#include "internal.h"
#include "syncwatch_hacl.h"

static Hacl_Hash_SHA2_state_t_256 view(swp_hash *hash)
{
    Hacl_Hash_SHA2_state_t_256 state = {
        .block_state = hash->words, .buf = hash->buffer, .total_len = hash->total
    };
    return state;
}
void swp_hash_init(swp_hash *hash)
{
    Hacl_Hash_SHA2_state_t_256 state;
    /* Match the pinned constructor's pointers/zero initialization without
     * calling its unchecked allocator. Vendor calls preserve these pointers. */
    memset(hash, 0, sizeof(*hash));
    state = view(hash);
    Hacl_Hash_SHA2_reset_256(&state);
    hash->total = state.total_len;
}
int swp_hash_update(swp_hash *hash, unsigned char *data, uint32_t size)
{
    Hacl_Hash_SHA2_state_t_256 state = view(hash);
    int result = Hacl_Hash_SHA2_update_256(&state, data, size) == Hacl_Streaming_Types_Success;
    hash->total = state.total_len;
    return result;
}
int swp_hash_matches(swp_hash *hash, const unsigned char expected[32])
{
    unsigned char digest[32];
    Hacl_Hash_SHA2_state_t_256 state = view(hash);
    Hacl_Hash_SHA2_digest_256(&state, digest);
    return memcmp(digest, expected, sizeof(digest)) == 0;
}
