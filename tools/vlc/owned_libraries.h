/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SYNCWATCH_VLC_OWNED_LIBRARIES_H
#define SYNCWATCH_VLC_OWNED_LIBRARIES_H
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <wchar.h>
static HMODULE owned_dependencies[128];
static unsigned owned_dependency_count;

static inline int load_owned_dependencies(void) {
    HMODULE owner;
    wchar_t directory[32768], pattern[32768], path[32768], loaded[32768];
    WIN32_FIND_DATAW entry;
    if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           libvlc_get_version(), &owner)) return 0;
    DWORD length = GetModuleFileNameW(owner, directory, 32768);
    if (!length || length >= 32768) return 0;
    wchar_t *separator = wcsrchr(directory, L'\\');
    if (!separator) return 0;
    *separator = L'\0';
    if (swprintf(pattern, 32768, L"%ls\\*.dll", directory) < 0) return 0;
    HANDLE search = FindFirstFileW(pattern, &entry);
    if (search == INVALID_HANDLE_VALUE) return 0;
    int result = 1;
    do {
        if (entry.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) continue;
        if (owned_dependency_count == 128 || swprintf(path, 32768, L"%ls\\%ls", directory, entry.cFileName) < 0) {
            result = 0; break;
        }
        // VLC deliberately limits plugin dependency lookup to System32. Load
        // the verified owned shared libraries first, with their own directory
        // and System32 as the only search roots. No PATH/CWD fallback is used.
        HMODULE module = LoadLibraryExW(path, NULL, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
        if (!module) { result = 0; break; }
        owned_dependencies[owned_dependency_count++] = module;
        length = GetModuleFileNameW(module, loaded, 32768);
        if (!length || length >= 32768 || _wcsicmp(path, loaded) != 0) { result = 0; break; }
    } while (FindNextFileW(search, &entry));
    if (result && GetLastError() != ERROR_NO_MORE_FILES) result = 0;
    FindClose(search);
    return result;
}

static inline void release_owned_dependencies(void) {
    while (owned_dependency_count) FreeLibrary(owned_dependencies[--owned_dependency_count]);
}

#else
#include <dlfcn.h>
static inline int load_owned_dependencies(void) { return 1; }
static inline void release_owned_dependencies(void) {}
#endif

static inline int owned_library(const char *expected) {
#ifdef _WIN32
    HMODULE module;
    char actual[32768], canonical[32768];
    if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            /* The public Windows header has no dllimport attribute. Use the
             * implementation's static inline version data, rather than its import thunk. */
            libvlc_get_version(), &module) ||
            !GetModuleFileNameA(module, actual, sizeof(actual)) || !_fullpath(canonical, expected, sizeof(canonical))) return 0;
    for (char *p = actual; *p; ++p) if (*p == '/') *p = '\\';
    for (char *p = canonical; *p; ++p) if (*p == '/') *p = '\\';
    return _stricmp(actual, canonical) == 0;
#else
    Dl_info info;
    if (!dladdr(libvlc_get_version(), &info)) return 0;
    char *actual = realpath(info.dli_fname, NULL), *canonical = realpath(expected, NULL);
    int matches = actual && canonical && strcmp(actual, canonical) == 0;
    free(actual); free(canonical);
    return matches;
#endif
}

#endif
