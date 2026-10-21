/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SYNCWATCH_PYTHON_PACKAGE_H
#define SYNCWATCH_PYTHON_PACKAGE_H
#include <stddef.h>
#include <stdint.h>
#include <wchar.h>

#define SW_PACKAGE_MAX_FILES 8192
#define SW_PACKAGE_MAX_ROOT 4096
#define SW_PACKAGE_MAX_RELATIVE 1024
#define SW_PACKAGE_MAX_DEPTH 32
#define SW_PACKAGE_MAX_NAME_CHARS 1048576
#define SW_PACKAGE_MAX_FILE_BYTES UINT64_C(536870912)
#define SW_PACKAGE_MAX_TOTAL_BYTES UINT64_C(1073741824)

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    const wchar_t *path;
    uint64_t size;
    unsigned char sha256[32];
} sw_package_file;
typedef struct sw_package sw_package;
typedef enum {
    SW_PACKAGE_OK = 0, SW_PACKAGE_INVALID_ARGUMENT, SW_PACKAGE_INVALID_MANIFEST,
    SW_PACKAGE_INVALID_ROOT, SW_PACKAGE_UNSAFE_ENTRY, SW_PACKAGE_UNEXPECTED_ENTRY,
    SW_PACKAGE_MISSING_ENTRY, SW_PACKAGE_SIZE_MISMATCH, SW_PACKAGE_DIGEST_MISMATCH,
    SW_PACKAGE_IO_FAILED, SW_PACKAGE_RESOURCE_LIMIT, SW_PACKAGE_PATH_NOT_FOUND,
    SW_PACKAGE_BUFFER_TOO_SMALL
} sw_package_result;
typedef enum { SW_PACKAGE_FILE = 1, SW_PACKAGE_DIRECTORY = 2 } sw_package_kind;

/* Expected inventory is trusted native caller data, sorted by ASCII case-folded
 * relative path. Names use portable ASCII components and '/' separators. Root
 * is a canonical absolute native path and may contain Unicode. Calls copy inputs.
 * On entry *output must be NULL; a failed open never publishes a package.
 * This records a completed scan, not an atomic filesystem snapshot or seal against
 * subsequent or concurrently hostile writes. A trusted immutable installation,
 * authentic inventory/source/ABI binding and verification before loading remain
 * caller prerequisites. Run I/O in the owned helper, with a parent watchdog.
 */
sw_package_result sw_package_open(const wchar_t *root, const sw_package_file *files,
                                  size_t count, sw_package **output);
/* The immutable result owns its copied inventory/root. Resolve performs no I/O
 * and does not revalidate later filesystem changes. Empty directory means root.
 * Failure leaves the caller's destination unchanged. Close once after readers stop.
 */
sw_package_result sw_package_resolve(const sw_package *package, const wchar_t *relative,
                                     sw_package_kind kind, wchar_t *output, size_t capacity);
void sw_package_close(sw_package *package);
#ifdef __cplusplus
}
#endif
#endif
