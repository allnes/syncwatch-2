/* SPDX-License-Identifier: Apache-2.0 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdlib.h>
#include <string.h>
#include "internal.h"

static wchar_t *native_path(const sw_package *p, const wchar_t *relative)
{
    wchar_t *path = swp_absolute(p, relative), *result;
    size_t length;
    if (!path) return NULL;
    length = wcslen(path);result = malloc((length + 5) * sizeof(wchar_t));
    if (result) { memcpy(result, L"\\\\?\\", 4 * sizeof(wchar_t));memcpy(result+4, path, (length+1)*sizeof(wchar_t)); }
    free(path);return result;
}
static int unchanged(const BY_HANDLE_FILE_INFORMATION *a, const BY_HANDLE_FILE_INFORMATION *b)
{
    return a->dwFileAttributes == b->dwFileAttributes && a->dwVolumeSerialNumber == b->dwVolumeSerialNumber &&
           a->nFileIndexHigh == b->nFileIndexHigh && a->nFileIndexLow == b->nFileIndexLow &&
           a->nFileSizeHigh == b->nFileSizeHigh && a->nFileSizeLow == b->nFileSizeLow && a->nNumberOfLinks == b->nNumberOfLinks &&
           !CompareFileTime(&a->ftLastWriteTime, &b->ftLastWriteTime);
}
static sw_package_result streams(const wchar_t *path)
{
    WIN32_FIND_STREAM_DATA data;
    HANDLE scan = FindFirstStreamW(path, FindStreamInfoStandard, &data, 0);
    sw_package_result status = SW_PACKAGE_OK;
    if (scan == INVALID_HANDLE_VALUE) return GetLastError() == ERROR_HANDLE_EOF ? SW_PACKAGE_OK : SW_PACKAGE_IO_FAILED;
    do {
        if (wcscmp(data.cStreamName, L"::$DATA")) { status = SW_PACKAGE_UNSAFE_ENTRY;break; }
    } while (FindNextStreamW(scan, &data));
    if (status == SW_PACKAGE_OK && GetLastError() != ERROR_HANDLE_EOF) status = SW_PACKAGE_IO_FAILED;
    FindClose(scan);return status;
}
static sw_package_result file_hash(const wchar_t *path, const sw_package_file *expected, DWORD volume)
{
    unsigned char buffer[65536];
    BY_HANDLE_FILE_INFORMATION before, after;
    uint64_t total = 0, size;
    swp_hash hash;
    sw_package_result status = SW_PACKAGE_IO_FAILED;
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
                              FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_SEQUENTIAL_SCAN, NULL);
    if (file == INVALID_HANDLE_VALUE) return status;
    if (!GetFileInformationByHandle(file, &before)) goto done;
    status = SW_PACKAGE_UNSAFE_ENTRY;
    if ((before.dwFileAttributes & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_DIRECTORY)) || before.nNumberOfLinks != 1 ||
        before.dwVolumeSerialNumber != volume || GetFileType(file) != FILE_TYPE_DISK) goto done;
    status = streams(path);
    if (status != SW_PACKAGE_OK) goto done;
    size = ((uint64_t)before.nFileSizeHigh << 32) | before.nFileSizeLow;
    status = SW_PACKAGE_SIZE_MISMATCH;
    if (size != expected->size) goto done;
    swp_hash_init(&hash);
    for (;;) {
        DWORD size_read;
        status = SW_PACKAGE_IO_FAILED;
        if (!ReadFile(file, buffer, sizeof(buffer), &size_read, NULL)) goto done;
        if (!size_read) break;
        status = SW_PACKAGE_SIZE_MISMATCH;
        if (size_read > expected->size - total) goto done;
        total += size_read;status = SW_PACKAGE_RESOURCE_LIMIT;
        if (!swp_hash_update(&hash, buffer, size_read)) goto done;
    }
    status = SW_PACKAGE_IO_FAILED;
    if (!GetFileInformationByHandle(file, &after)) goto done;
    status = SW_PACKAGE_UNSAFE_ENTRY;
    if (!unchanged(&before, &after)) goto done;
    status = SW_PACKAGE_SIZE_MISMATCH;
    if (total != expected->size) goto done;
    status = swp_hash_matches(&hash, expected->sha256) ? SW_PACKAGE_OK : SW_PACKAGE_DIGEST_MISMATCH;
done:
    CloseHandle(file);return status;
}
static sw_package_result walk(const sw_package *p, const wchar_t *prefix, DWORD volume, size_t *seen, size_t depth)
{
    wchar_t *path = native_path(p, prefix), *pattern = NULL;
    HANDLE directory = INVALID_HANDLE_VALUE, scan = INVALID_HANDLE_VALUE;
    BY_HANDLE_FILE_INFORMATION before, after;
    WIN32_FIND_DATAW data;
    sw_package_result status = SW_PACKAGE_RESOURCE_LIMIT;
    size_t length;
    if (!path) return status;
    if (depth > SW_PACKAGE_MAX_DEPTH) goto done;
    directory = CreateFileW(path, FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES,
                            FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING,
                            FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, NULL);
    status = SW_PACKAGE_IO_FAILED;
    if (directory == INVALID_HANDLE_VALUE || !GetFileInformationByHandle(directory, &before)) goto done;
    status = SW_PACKAGE_UNSAFE_ENTRY;
    if (!(before.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || (before.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) ||
        before.dwVolumeSerialNumber != volume) goto done;
    status = streams(path);
    if (status != SW_PACKAGE_OK) goto done;
    length = wcslen(path);pattern = malloc((length + 3) * sizeof(wchar_t));status = SW_PACKAGE_RESOURCE_LIMIT;
    if (!pattern) goto done;
    memcpy(pattern, path, length*sizeof(wchar_t));memcpy(pattern+length, L"\\*", 3*sizeof(wchar_t));
    scan = FindFirstFileW(pattern, &data);status = SW_PACKAGE_IO_FAILED;
    if (scan == INVALID_HANDLE_VALUE) { if (GetLastError() == ERROR_FILE_NOT_FOUND) status = SW_PACKAGE_OK;goto checked; }
    do {
        wchar_t relative[SW_PACKAGE_MAX_RELATIVE];
        size_t index;
        if (!wcscmp(data.cFileName, L".") || !wcscmp(data.cFileName, L"..")) continue;
        status = SW_PACKAGE_UNEXPECTED_ENTRY;
        if (!swp_child(prefix, data.cFileName, relative)) goto done;
        status = SW_PACKAGE_UNSAFE_ENTRY;
        if (data.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) goto done;
        if (data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            status = SW_PACKAGE_UNEXPECTED_ENTRY;
            if (!swp_directory(p, relative)) goto done;
            status = walk(p, relative, volume, seen, depth+1);
        } else {
            wchar_t *file;
            index = swp_find(p, relative);status = SW_PACKAGE_UNEXPECTED_ENTRY;
            if (index == p->count || wcscmp(p->files[index].path, relative)) goto done;
            file = native_path(p, relative);status = SW_PACKAGE_RESOURCE_LIMIT;
            if (!file) goto done;
            status = file_hash(file, &p->files[index], volume);free(file);
            if (status == SW_PACKAGE_OK) ++*seen;
        }
        if (status != SW_PACKAGE_OK) goto done;
    } while (FindNextFileW(scan, &data));
    status = GetLastError() == ERROR_NO_MORE_FILES ? SW_PACKAGE_OK : SW_PACKAGE_IO_FAILED;
checked:
    if (status == SW_PACKAGE_OK) {
        if (!GetFileInformationByHandle(directory, &after)) status = SW_PACKAGE_IO_FAILED;
        else if (!unchanged(&before, &after)) status = SW_PACKAGE_UNSAFE_ENTRY;
    }
done:
    if (scan != INVALID_HANDLE_VALUE) FindClose(scan);
    if (directory != INVALID_HANDLE_VALUE) CloseHandle(directory);
    free(pattern);free(path);return status;
}
sw_package_result swp_platform_verify(const sw_package *p)
{
    wchar_t *path = native_path(p, L"");
    size_t i, seen = 0;
    DWORD volume = 0;
    sw_package_result status = SW_PACKAGE_RESOURCE_LIMIT;
    if (!path) return status;
    {
        wchar_t drive[] = {p->root[0], L':', L'\\', 0};
        UINT kind = GetDriveTypeW(drive);
        if (kind == DRIVE_REMOTE) { free(path);return SW_PACKAGE_UNSAFE_ENTRY; }
        if (kind == DRIVE_UNKNOWN || kind == DRIVE_NO_ROOT_DIR) { free(path);return SW_PACKAGE_IO_FAILED; }
    }
    /* Open every ancestor as a reparse point before accepting the root path. */
    for (i = 7;; ++i) {
        if (!path[i] || path[i] == L'\\') {
            wchar_t saved = path[i];
            BY_HANDLE_FILE_INFORMATION info;
            HANDLE handle;
            path[i] = 0;handle = CreateFileW(path, FILE_READ_ATTRIBUTES,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL, OPEN_EXISTING,
                FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, NULL);path[i] = saved;
            status = SW_PACKAGE_IO_FAILED;
            if (handle == INVALID_HANDLE_VALUE) goto done;
            if (!GetFileInformationByHandle(handle, &info)) { CloseHandle(handle);goto done; }
            CloseHandle(handle);status = SW_PACKAGE_UNSAFE_ENTRY;
            if (!(info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || (info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)) goto done;
            volume = info.dwVolumeSerialNumber;
            if (!saved) break;
        }
    }
    status = walk(p, L"", volume, &seen, 0);
    if (status == SW_PACKAGE_OK && seen != p->count) status = SW_PACKAGE_MISSING_ENTRY;
done:
    free(path);return status;
}
