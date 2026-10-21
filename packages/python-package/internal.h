/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SYNCWATCH_PACKAGE_INTERNAL_H
#define SYNCWATCH_PACKAGE_INTERNAL_H
#include "package.h"
struct sw_package { wchar_t *root; sw_package_file *files; size_t count; };
int swp_relative(const wchar_t *name);
int swp_fold_prefix(const wchar_t *value, const wchar_t *prefix);
int swp_same_directories(const wchar_t *left, const wchar_t *right);
int swp_fold_compare(const wchar_t *left, const wchar_t *right);
int swp_root(const wchar_t *root);
wchar_t *swp_copy(const wchar_t *value);
wchar_t *swp_absolute(const sw_package *package, const wchar_t *relative);
size_t swp_find(const sw_package *package, const wchar_t *relative);
int swp_directory(const sw_package *package, const wchar_t *relative);
int swp_child(const wchar_t *parent, const wchar_t *name, wchar_t *result);
sw_package_result swp_platform_verify(const sw_package *package);
#include "syncwatch_hacl.h"
/* Match the pinned public SHA-256 state layout; no vendor allocator is called. */
typedef struct {
    Hacl_Hash_SHA2_state_t_256 state;
    uint32_t words[8];
    uint8_t buffer[64];
} swp_hash;
void swp_hash_init(swp_hash *hash);
int swp_hash_update(swp_hash *hash, unsigned char *data, uint32_t size);
int swp_hash_matches(swp_hash *hash, const unsigned char expected[32]);
#endif
