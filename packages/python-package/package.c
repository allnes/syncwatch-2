/* SPDX-License-Identifier: Apache-2.0 */
#include <stdlib.h>
#include <string.h>
#include "internal.h"

void sw_package_close(sw_package *package)
{
    size_t i;
    if (!package) return;
    if (package->files) for (i = 0; i < package->count; ++i) free((void *)package->files[i].path);
    free(package->files);free(package->root);free(package);
}
sw_package_result sw_package_open(const wchar_t *root, const sw_package_file *files, size_t count, sw_package **output)
{
    sw_package *p;
    size_t i, chars = 0;
    uint64_t bytes = 0;
    sw_package_result status = SW_PACKAGE_INVALID_MANIFEST;
    if (!output || *output || !files || !count) return SW_PACKAGE_INVALID_ARGUMENT;
    if (count > SW_PACKAGE_MAX_FILES) return SW_PACKAGE_RESOURCE_LIMIT;
    if (!swp_root(root)) return SW_PACKAGE_INVALID_ROOT;
    p = calloc(1, sizeof(*p));
    if (!p) return SW_PACKAGE_RESOURCE_LIMIT;
    p->count = count;p->files = calloc(count, sizeof(*p->files));p->root = swp_copy(root);
    if (!p->files || !p->root) { status = SW_PACKAGE_RESOURCE_LIMIT;goto done; }
    for (i = 0; i < count; ++i) {
        size_t length;
        /* Copy each bounded string before examining it again. Caller inputs
         * must remain valid for this call; accepted results never borrow them. */
        if (!swp_relative(files[i].path)) goto done;
        length = wcslen(files[i].path);
        if (length + 1 > SW_PACKAGE_MAX_NAME_CHARS - chars || files[i].size > SW_PACKAGE_MAX_FILE_BYTES ||
            files[i].size > SW_PACKAGE_MAX_TOTAL_BYTES - bytes) { status = SW_PACKAGE_RESOURCE_LIMIT;goto done; }
        chars += length + 1;bytes += files[i].size;
        p->files[i] = files[i];p->files[i].path = swp_copy(files[i].path);
        if (!p->files[i].path) { status = SW_PACKAGE_RESOURCE_LIMIT;goto done; }
        if (i) {
            size_t previous = wcslen(p->files[i-1].path);
            if (swp_fold_compare(p->files[i-1].path, p->files[i].path) >= 0) goto done;
            if (swp_fold_prefix(p->files[i].path, p->files[i-1].path) && p->files[i].path[previous] == L'/') goto done;
            if (!swp_same_directories(p->files[i-1].path, p->files[i].path)) goto done;
        }
    }
    status = swp_platform_verify(p);
    if (status == SW_PACKAGE_OK) { *output = p;return status; }
done:
    sw_package_close(p);return status;
}
sw_package_result sw_package_resolve(const sw_package *p, const wchar_t *relative, sw_package_kind kind, wchar_t *output, size_t capacity)
{
    size_t index, length;
    wchar_t *absolute;
    if (!p || !relative || !output || (kind != SW_PACKAGE_FILE && kind != SW_PACKAGE_DIRECTORY)) return SW_PACKAGE_INVALID_ARGUMENT;
    if (*relative && !swp_relative(relative)) return SW_PACKAGE_PATH_NOT_FOUND;
    if (kind == SW_PACKAGE_FILE) {
        index = swp_find(p, relative);
        if (index == p->count || wcscmp(p->files[index].path, relative)) return SW_PACKAGE_PATH_NOT_FOUND;
    } else if (!swp_directory(p, relative)) return SW_PACKAGE_PATH_NOT_FOUND;
    absolute = swp_absolute(p, relative);
    if (!absolute) return SW_PACKAGE_RESOURCE_LIMIT;
    length = wcslen(absolute) + 1;
    if (length > capacity) { free(absolute);return SW_PACKAGE_BUFFER_TOO_SMALL; }
    memcpy(output, absolute, length * sizeof(wchar_t));free(absolute);return SW_PACKAGE_OK;
}
