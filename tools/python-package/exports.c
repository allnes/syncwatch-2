/* SPDX-License-Identifier: Apache-2.0 */
#include "python_paths.h"
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif
/* Test-only shared entry points call the actual statically linked public API.
 * Neither this module nor the developer Python/ctypes runtime is distributed. */
EXPORT size_t sw_test_file_size(void) { return sizeof(sw_package_file); }
EXPORT size_t sw_test_paths_size(void) { return sizeof(sw_python_paths); }
EXPORT sw_package_result sw_test_open(const wchar_t *root, const sw_package_file *files, size_t count, sw_package **output)
{ return sw_package_open(root, files, count, output); }
EXPORT void sw_test_close(sw_package *p) { sw_package_close(p); }
EXPORT sw_package_result sw_test_resolve(const sw_package *p, const wchar_t *relative, sw_package_kind kind, wchar_t *output, size_t capacity)
{ return sw_package_resolve(p, relative, kind, output, capacity); }
EXPORT sw_package_result sw_test_create_paths(const sw_package *p, const sw_python_package_layout *layout, sw_python_package_paths **out)
{ return sw_python_package_create_paths(p, layout, out); }
EXPORT void sw_test_close_paths(sw_python_package_paths *p) { sw_python_package_close_paths(p); }
EXPORT const sw_python_paths *sw_test_paths_view(const sw_python_package_paths *p) { return sw_python_package_startup_paths(p); }
EXPORT const wchar_t *sw_test_library(const sw_python_package_paths *p) { return sw_python_package_library(p); }
