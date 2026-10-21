/* SPDX-License-Identifier: Apache-2.0 */
#include <stdlib.h>
#include <string.h>
#include "internal.h"
#include "python_paths.h"
struct sw_python_package_paths {
    sw_python_paths startup;
    wchar_t *root, *executable, *library;
    wchar_t *search[SW_PYTHON_MAX_SEARCH_PATHS];
};
void sw_python_package_close_paths(sw_python_package_paths *p)
{
    size_t i;
    if (!p) return;
    for (i = 0; i < SW_PYTHON_MAX_SEARCH_PATHS; ++i) free(p->search[i]);
    free(p->root);free(p->executable);free(p->library);free(p);
}
static sw_package_result resolve(const sw_package *package, const wchar_t *relative, sw_package_kind kind, wchar_t **out)
{
    wchar_t buffer[SW_PACKAGE_MAX_ROOT + SW_PACKAGE_MAX_RELATIVE + 1];
    sw_package_result status = sw_package_resolve(package, relative, kind, buffer, sizeof(buffer)/sizeof(*buffer));
    if (status != SW_PACKAGE_OK) return status;
    *out = swp_copy(buffer);
    return *out ? SW_PACKAGE_OK : SW_PACKAGE_RESOURCE_LIMIT;
}
sw_package_result sw_python_package_create_paths(const sw_package *package, const sw_python_package_layout *layout, sw_python_package_paths **output)
{
    sw_python_package_paths *p;
    sw_package_result status;
    size_t i, j;
    if (!package || !layout || !output || *output || !layout->search || !layout->search_count ||
        layout->search_count > SW_PYTHON_MAX_SEARCH_PATHS || !swp_relative(layout->executable) ||
        !wcschr(layout->executable, L'/') || !swp_relative(layout->library) ||
        !wcscmp(layout->executable, layout->library)) return SW_PACKAGE_INVALID_ARGUMENT;
    p = calloc(1, sizeof(*p));
    if (!p) return SW_PACKAGE_RESOURCE_LIMIT;
    status = resolve(package, L"", SW_PACKAGE_DIRECTORY, &p->root);
    if (status != SW_PACKAGE_OK) goto done;
    status = resolve(package, layout->executable, SW_PACKAGE_FILE, &p->executable);
    if (status != SW_PACKAGE_OK) goto done;
    status = resolve(package, layout->library, SW_PACKAGE_FILE, &p->library);
    if (status != SW_PACKAGE_OK) goto done;
    for (i = 0; i < layout->search_count; ++i) {
        size_t length;
        if (!swp_relative(layout->search[i])) { status = SW_PACKAGE_INVALID_ARGUMENT;goto done; }
        for (j = 0; j < i; ++j) {
            if (!swp_fold_compare(layout->search[j], layout->search[i])) { status = SW_PACKAGE_INVALID_ARGUMENT;goto done; }
        }
        length = wcslen(layout->search[i]);
        status = resolve(package, layout->search[i], SW_PACKAGE_DIRECTORY, &p->search[i]);
        if (status == SW_PACKAGE_PATH_NOT_FOUND && length >= 4 && !wcscmp(layout->search[i] + length-4, L".zip"))
            status = resolve(package, layout->search[i], SW_PACKAGE_FILE, &p->search[i]);
        if (status != SW_PACKAGE_OK) goto done;
    }
#define SW_PREFIX(name) p->startup.name = p->root;
    SW_PYTHON_PATH_FIELDS(SW_PREFIX)
#undef SW_PREFIX
    p->startup.program_name = p->executable;p->startup.executable = p->executable;
    p->startup.base_executable = p->executable;
    p->startup.search_path_count = layout->search_count;p->startup.search_paths = (const wchar_t *const *)p->search;
    *output = p;return SW_PACKAGE_OK;
done:
    sw_python_package_close_paths(p);return status;
}
const sw_python_paths *sw_python_package_startup_paths(const sw_python_package_paths *p) { return p ? &p->startup : NULL; }
const wchar_t *sw_python_package_library(const sw_python_package_paths *p) { return p ? p->library : NULL; }
