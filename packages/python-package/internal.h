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
typedef struct swp_hash swp_hash;
swp_hash *swp_hash_create(void);
int swp_hash_update(swp_hash *hash, unsigned char *data, uint32_t size);
int swp_hash_matches(swp_hash *hash, const unsigned char expected[32]);
void swp_hash_close(swp_hash *hash);
#endif
