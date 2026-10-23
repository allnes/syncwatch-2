/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE
#include "vlc_api.h"
#include "../include/syncwatch_playback.h"
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <wchar.h>
struct sw_library { HMODULE main, dependencies[128]; unsigned count; };
static void *symbol(sw_library *lib, const char *name) {
    FARPROC proc = GetProcAddress(lib->main, name);
    void *result = NULL;
    _Static_assert(sizeof(result) == sizeof(proc), "Native pointer size");
    memcpy(&result, &proc, sizeof(result));
    return result;
}
static int open_library(const char *path, sw_library *lib) {
    wchar_t full[32768], directory[32768], pattern[32768], current[32768], actual[32768];
    if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, full, 32768) ||
        wcslen(full) < 3 || full[1] != L':' || (full[2] != L'\\' && full[2] != L'/')) return 0;
    DWORD size = GetFullPathNameW(full, 32768, directory, NULL);
    if (!size || size >= 32768) return 0;
    wcscpy(full, directory);
    wchar_t *separator = wcsrchr(directory, L'\\');
    if (!separator) return 0;
    *separator = 0;
    if (swprintf(pattern, 32768, L"%ls\\*.dll", directory) < 0) return 0;
    WIN32_FIND_DATAW entry;
    HANDLE search = FindFirstFileW(pattern, &entry);
    if (search == INVALID_HANDLE_VALUE) return 0;
    int ok = 1;
    do {
        if (entry.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) continue;
        if (lib->count == 128 || swprintf(current, 32768, L"%ls\\%ls", directory, entry.cFileName) < 0) { ok = 0; break; }
        HMODULE module = LoadLibraryExW(current, NULL, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
        if (!module) { ok = 0; break; }
        lib->dependencies[lib->count++] = module;
        DWORD length = GetModuleFileNameW(module, actual, 32768);
        if (!length || length >= 32768 || _wcsicmp(current, actual)) { ok = 0; break; }
        if (!_wcsicmp(full, actual)) lib->main = module;
    } while (FindNextFileW(search, &entry));
    if (ok && GetLastError() != ERROR_NO_MORE_FILES) ok = 0;
    FindClose(search);
    return ok && lib->main;
}
void sw_library_close(sw_library *lib) {
    if (!lib) return;
    while (lib->count) FreeLibrary(lib->dependencies[--lib->count]);
    free(lib);
}
#else
#include <dlfcn.h>
struct sw_library { void *main; };
static void *symbol(sw_library *lib, const char *name) { return dlsym(lib->main, name); }
static int open_library(const char *path, sw_library *lib) {
    if (path[0] != '/') return 0;
    lib->main = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    return lib->main != NULL;
}
void sw_library_close(sw_library *lib) {
    if (!lib) return;
    if (lib->main) dlclose(lib->main);
    free(lib);
}
#endif

int sw_library_open(const char *path, sw_vlc_api *api, int output, sw_library **result) {
    *result = NULL;
    sw_library *lib = calloc(1, sizeof(*lib));
    if (!lib || !open_library(path, lib)) { sw_library_close(lib); return 0; }
#define SW_BIND(return_type, name, arguments) { \
    void *address = symbol(lib, #name); \
    _Static_assert(sizeof(address) == sizeof(api->name), "Function pointer size"); \
    if (!address) goto failed; \
    memcpy(&api->name, &address, sizeof(address)); }
    SW_VLC_FUNCTIONS(SW_BIND)
#undef SW_BIND
    if (output != SW_OUTPUT_HEADLESS) {
        void *address = symbol(lib, output == SW_OUTPUT_APPKIT ? "libvlc_media_player_set_nsobject" : "libvlc_media_player_set_hwnd");
        if (!address) goto failed;
        memcpy(&api->set_surface, &address, sizeof(address));
    }
#ifndef _WIN32
    /* Reject interposition or an already loaded library from another package. */
    Dl_info info;
    char *actual = NULL, *expected = realpath(path, NULL);
    if (dladdr(api->libvlc_get_version(), &info)) actual = realpath(info.dli_fname, NULL);
    int owned = actual && expected && !strcmp(actual, expected);
    free(actual); free(expected);
    if (!owned) goto failed;
#endif
    *result = lib;
    return 1;
failed:
    sw_library_close(lib);
    memset(api, 0, sizeof(*api));
    return 0;
}
