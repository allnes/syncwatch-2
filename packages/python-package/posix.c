/* SPDX-License-Identifier: Apache-2.0 */
#ifdef __APPLE__
#define _DARWIN_C_SOURCE 1
#endif
#define _POSIX_C_SOURCE 200809L
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "internal.h"

static int unchanged(const struct stat *a, const struct stat *b)
{
#ifdef __APPLE__
#define MT st_mtimespec
#define CT st_ctimespec
#else
#define MT st_mtim
#define CT st_ctim
#endif
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino && a->st_mode == b->st_mode &&
           a->st_nlink == b->st_nlink && a->st_size == b->st_size &&
           a->MT.tv_sec == b->MT.tv_sec && a->MT.tv_nsec == b->MT.tv_nsec &&
           a->CT.tv_sec == b->CT.tv_sec && a->CT.tv_nsec == b->CT.tv_nsec;
#undef MT
#undef CT
}
static char *utf8(const wchar_t *root)
{
    size_t i, n = 0, length = wcslen(root);
    char *result = malloc(length * 4 + 1);
    if (!result) return NULL;
    for (i = 0; i < length; ++i) {
        uint32_t c = (uint32_t)root[i];
        if (c < 0x80) result[n++] = (char)c;
        else {
            if (c >= 0x10000) { result[n++] = (char)(0xf0 | (c >> 18));result[n++] = (char)(0x80 | ((c >> 12) & 63)); }
            else if (c >= 0x800) result[n++] = (char)(0xe0 | (c >> 12));
            else result[n++] = (char)(0xc0 | (c >> 6));
            if (c >= 0x800) result[n++] = (char)(0x80 | ((c >> 6) & 63));
            result[n++] = (char)(0x80 | (c & 63));
        }
    }
    result[n] = 0;return result;
}
static sw_package_result file_hash(int parent, const char *name, const struct stat *entry, const sw_package_file *expected, dev_t device)
{
    unsigned char buffer[65536];
    struct stat before, after;
    uint64_t total = 0;
    swp_hash hash;
    sw_package_result status = SW_PACKAGE_IO_FAILED;
    int fd = openat(parent, name, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    if (fd < 0) return errno == ELOOP ? SW_PACKAGE_UNSAFE_ENTRY : SW_PACKAGE_IO_FAILED;
    if (fstat(fd, &before)) goto done;
    status = SW_PACKAGE_UNSAFE_ENTRY;
    if (!S_ISREG(before.st_mode) || before.st_nlink != 1 || before.st_dev != device || !unchanged(entry, &before)) goto done;
    status = SW_PACKAGE_SIZE_MISMATCH;
    if (before.st_size < 0 || (uint64_t)before.st_size != expected->size) goto done;
    swp_hash_init(&hash);
    for (;;) {
        ssize_t n = read(fd, buffer, sizeof(buffer));
        if (n < 0 && errno == EINTR) continue;
        status = SW_PACKAGE_IO_FAILED;
        if (n < 0) goto done;
        if (!n) break;
        status = SW_PACKAGE_SIZE_MISMATCH;
        if ((uint64_t)n > expected->size - total) goto done;
        total += (uint64_t)n;
        status = SW_PACKAGE_RESOURCE_LIMIT;
        if (!swp_hash_update(&hash, buffer, (uint32_t)n)) goto done;
    }
    status = SW_PACKAGE_IO_FAILED;
    if (fstat(fd, &after)) goto done;
    status = SW_PACKAGE_UNSAFE_ENTRY;
    if (!unchanged(&before, &after)) goto done;
    status = SW_PACKAGE_SIZE_MISMATCH;
    if (total != expected->size) goto done;
    status = swp_hash_matches(&hash, expected->sha256) ? SW_PACKAGE_OK : SW_PACKAGE_DIGEST_MISMATCH;
done:
    close(fd);return status;
}
static sw_package_result walk(const sw_package *p, int fd, const wchar_t *prefix, dev_t device, size_t *seen, size_t depth)
{
    struct stat before, after;
    sw_package_result status = SW_PACKAGE_IO_FAILED;
    int copied;
    DIR *directory;
    if (depth > SW_PACKAGE_MAX_DEPTH) return SW_PACKAGE_RESOURCE_LIMIT;
    if (fstat(fd, &before)) return status;
    if (!S_ISDIR(before.st_mode) || before.st_dev != device) return SW_PACKAGE_UNSAFE_ENTRY;
    copied = fcntl(fd, F_DUPFD_CLOEXEC, 0);
    if (copied < 0) return status;
    directory = fdopendir(copied);
    if (!directory) { close(copied);return status; }
    for (;;) {
        struct dirent *item;
        struct stat info;
        wchar_t name[SW_PACKAGE_MAX_RELATIVE], relative[SW_PACKAGE_MAX_RELATIVE];
        size_t i, index;
        errno = 0;item = readdir(directory);
        if (!item) { status = errno ? SW_PACKAGE_IO_FAILED : SW_PACKAGE_OK;break; }
        if (!strcmp(item->d_name, ".") || !strcmp(item->d_name, "..")) continue;
        status = SW_PACKAGE_UNEXPECTED_ENTRY;
        for (i = 0; item->d_name[i] && i < SW_PACKAGE_MAX_RELATIVE - 1; ++i) {
            if ((unsigned char)item->d_name[i] >= 128) goto done;
            name[i] = (unsigned char)item->d_name[i];
        }
        if (item->d_name[i]) goto done;
        name[i] = 0;
        if (!swp_child(prefix, name, relative)) goto done;
        status = SW_PACKAGE_IO_FAILED;
        if (fstatat(fd, item->d_name, &info, AT_SYMLINK_NOFOLLOW)) goto done;
        status = SW_PACKAGE_UNSAFE_ENTRY;
        if (S_ISLNK(info.st_mode) || info.st_dev != device) goto done;
        if (S_ISDIR(info.st_mode)) {
            int child;
            status = SW_PACKAGE_UNEXPECTED_ENTRY;
            if (!swp_directory(p, relative)) goto done;
            child = openat(fd, item->d_name, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
            status = SW_PACKAGE_UNSAFE_ENTRY;
            if (child < 0) goto done;
            if (fstat(child, &after) || !unchanged(&info, &after)) { close(child);goto done; }
            status = walk(p, child, relative, device, seen, depth+1);close(child);
            if (status != SW_PACKAGE_OK) goto done;
        } else {
            if (!S_ISREG(info.st_mode) || info.st_nlink != 1) goto done;
            index = swp_find(p, relative);status = SW_PACKAGE_UNEXPECTED_ENTRY;
            if (index == p->count || wcscmp(p->files[index].path, relative)) goto done;
            status = file_hash(fd, item->d_name, &info, &p->files[index], device);
            if (status != SW_PACKAGE_OK) goto done;
            ++*seen;
        }
    }
    if (status == SW_PACKAGE_OK) {
        if (fstat(fd, &after)) status = SW_PACKAGE_IO_FAILED;
        else if (!unchanged(&before, &after)) status = SW_PACKAGE_UNSAFE_ENTRY;
    }
done:
    closedir(directory);return status;
}
sw_package_result swp_platform_verify(const sw_package *p)
{
    char *name = utf8(p->root), *start, *cursor;
    int fd = -1;
    size_t seen = 0;
    struct stat root;
    sw_package_result status = SW_PACKAGE_RESOURCE_LIMIT;
    if (!name) return status;
    fd = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);status = SW_PACKAGE_IO_FAILED;
    if (fd < 0) goto done;
    start = name + 1;
    for (cursor = start;; ++cursor) {
        if (!*cursor || *cursor == '/') {
            int child, last = !*cursor;
            *cursor = 0;child = openat(fd, start, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
            if (child < 0) { status = errno == ELOOP || errno == ENOTDIR ? SW_PACKAGE_UNSAFE_ENTRY : SW_PACKAGE_IO_FAILED;goto done; }
            close(fd);fd = child;
            if (last) break;
            start = cursor + 1;
        }
    }
    if (fstat(fd, &root)) goto done;
    status = walk(p, fd, L"", root.st_dev, &seen, 0);
    if (status == SW_PACKAGE_OK && seen != p->count) status = SW_PACKAGE_MISSING_ENTRY;
done:
    if (fd >= 0) close(fd);
    free(name);return status;
}
