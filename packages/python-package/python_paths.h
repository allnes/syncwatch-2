/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SYNCWATCH_PYTHON_PACKAGE_PATHS_H
#define SYNCWATCH_PYTHON_PACKAGE_PATHS_H
#include "package.h"
#ifdef __cplusplus
extern "C" {
#endif

#include "startup.h"
typedef struct {
    const wchar_t *executable;
    const wchar_t *library;
    size_t search_count;
    const wchar_t *const *search;
} sw_python_package_layout;
typedef struct sw_python_package_paths sw_python_package_paths;
/* All paths are relative to a successfully verified package. Executable must
 * have an internal parent directory, keeping adjacent configuration probes
 * inside the closed tree. Search entries are declared directories or ZIP files.
 * Result owns all strings and survives closing the inventory snapshot.
 * This maps paths only; it neither loads a library nor initializes Python.
 */
sw_package_result sw_python_package_create_paths(const sw_package *package,
    const sw_python_package_layout *layout, sw_python_package_paths **output);
const sw_python_paths *sw_python_package_startup_paths(const sw_python_package_paths *paths);
const wchar_t *sw_python_package_library(const sw_python_package_paths *paths);
void sw_python_package_close_paths(sw_python_package_paths *paths);
#ifdef __cplusplus
}
#endif
#endif
