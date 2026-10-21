/* SPDX-License-Identifier: Apache-2.0 */
#include <stdlib.h>
#include <string.h>
#include "internal.h"
#include "syncwatch_hacl.h"
struct swp_hash { Hacl_Hash_SHA2_state_t_256 *state; };
swp_hash *swp_hash_create(void)
{
    swp_hash *h = malloc(sizeof(*h));
    if (!h) return NULL;
    h->state = Hacl_Hash_SHA2_malloc_256();
    if (!h->state) { free(h);return NULL; }
    return h;
}
int swp_hash_update(swp_hash *h, unsigned char *data, uint32_t size)
{
    return Hacl_Hash_SHA2_update_256(h->state, data, size) == Hacl_Streaming_Types_Success;
}
int swp_hash_matches(swp_hash *h, const unsigned char expected[32])
{
    unsigned char digest[32];
    Hacl_Hash_SHA2_digest_256(h->state, digest);
    return memcmp(digest, expected, sizeof(digest)) == 0;
}
void swp_hash_close(swp_hash *h)
{
    if (h) { Hacl_Hash_SHA2_free_256(h->state);free(h); }
}
