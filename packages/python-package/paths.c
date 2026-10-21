/* SPDX-License-Identifier: Apache-2.0 */
#include <stdlib.h>
#include <string.h>
#include "internal.h"

static wchar_t lower(wchar_t c) { return c >= L'A' && c <= L'Z' ? c + (L'a' - L'A') : c; }
int swp_fold_compare(const wchar_t *a, const wchar_t *b)
{
    while (*a && lower(*a) == lower(*b)) { ++a; ++b; }
    return lower(*a) < lower(*b) ? -1 : lower(*a) > lower(*b);
}
int swp_fold_prefix(const wchar_t *value, const wchar_t *prefix)
{
    while (*prefix) if (lower(*value++) != lower(*prefix++)) return 0;
    return 1;
}
int swp_same_directories(const wchar_t *a, const wchar_t *b)
{
    int different_case = 0;
    while (*a && lower(*a) == lower(*b)) {
        if (*a != *b) different_case = 1;
        if (*a == L'/' && different_case) return 0;
        ++a;++b;
    }
    return 1;
}
static int segment(const wchar_t *s, size_t length)
{
    wchar_t stem[5] = {0};
    size_t i, stem_length = 0;
    if (!length || length > 255 || s[length-1] == L'.') return 0;
    if ((length == 1 && s[0] == L'.') || (length == 2 && s[0] == L'.' && s[1] == L'.')) return 0;
    for (i = 0; i < length; ++i) {
        wchar_t c = s[i];
        if (!((c >= L'a' && c <= L'z') || (c >= L'A' && c <= L'Z') ||
              (c >= L'0' && c <= L'9') || c == L'.' || c == L'_' || c == L'-')) return 0;
        if (i < 4 && c != L'.') stem[i] = lower(c);
        if (c == L'.') break;
    }
    while (stem_length < length && s[stem_length] != L'.') ++stem_length;
    if (!wcscmp(stem, L"con") || !wcscmp(stem, L"prn") || !wcscmp(stem, L"aux") || !wcscmp(stem, L"nul")) return 0;
    if (stem_length == 4 && (!wcsncmp(stem, L"com", 3) || !wcsncmp(stem, L"lpt", 3)) && stem[3] >= L'1' && stem[3] <= L'9') return 0;
    for (; i < length; ++i) {
        wchar_t c = s[i];
        if (!((c >= L'a' && c <= L'z') || (c >= L'A' && c <= L'Z') ||
              (c >= L'0' && c <= L'9') || c == L'.' || c == L'_' || c == L'-')) return 0;
    }
    return 1;
}
static int forbidden(const wchar_t *name)
{
    wchar_t folded[SW_PACKAGE_MAX_RELATIVE];
    size_t i, length = wcslen(name);
    for (i = 0; i <= length; ++i) folded[i] = lower(name[i]);
    return !wcscmp(folded, L"pyvenv.cfg") || !wcsncmp(folded, L"sitecustomize.", 14) ||
           !wcsncmp(folded, L"usercustomize.", 14) ||
           (length >= 4 && !wcscmp(folded + length - 4, L".pth")) ||
           (length >= 5 && !wcscmp(folded + length - 5, L"._pth"));
}
int swp_relative(const wchar_t *name)
{
    size_t length = 0, start = 0, depth = 1, i;
    if (!name) return 0;
    while (length < SW_PACKAGE_MAX_RELATIVE && name[length]) ++length;
    if (!length || length == SW_PACKAGE_MAX_RELATIVE) return 0;
    for (i = 0; i <= length; ++i) {
        if (name[i] == L'/' || !name[i]) {
            if (!segment(name + start, i - start)) return 0;
            if (name[i] && ++depth > SW_PACKAGE_MAX_DEPTH) return 0;
            start = i + 1;
        }
    }
    return !forbidden(wcsrchr(name, L'/') ? wcsrchr(name, L'/') + 1 : name);
}
int swp_root(const wchar_t *root)
{
    size_t length = 0, i, start;
    if (!root) return 0;
    while (length < SW_PACKAGE_MAX_ROOT && root[length]) ++length;
    if (!length || length == SW_PACKAGE_MAX_ROOT) return 0;
#ifdef _WIN32
    if (length < 4 || !((root[0] >= L'A' && root[0] <= L'Z') || (root[0] >= L'a' && root[0] <= L'z')) || root[1] != L':' || root[2] != L'\\') return 0;
    start = 3;
#else
    if (length < 2 || root[0] != L'/') return 0;
    start = 1;
#endif
    for (i = start; i <= length; ++i) {
        wchar_t c = root[i];
#ifdef _WIN32
        if ((c >= 0xd800 && c <= 0xdbff) && i + 1 < length && root[i+1] >= 0xdc00 && root[i+1] <= 0xdfff) { ++i; continue; }
        if ((c >= 0xd800 && c <= 0xdfff) || c == L':' || c == L'/' || c == L'"' || c == L'<' || c == L'>' || c == L'|' || c == L'?' || c == L'*') return 0;
        if (c == L'\\' || !c) {
#else
        if (c > 0x10ffff || (c >= 0xd800 && c <= 0xdfff) || c == L'\\') return 0;
        if (c == L'/' || !c) {
#endif
            size_t n = i - start;
            if (!n || (n == 1 && root[start] == L'.') || (n == 2 && root[start] == L'.' && root[start+1] == L'.')) return 0;
#ifdef _WIN32
            if (root[i-1] == L'.' || root[i-1] == L' ') return 0;
#endif
            start = i + 1;
        } else if (c < 32 || c == 127) return 0;
    }
    return 1;
}
wchar_t *swp_copy(const wchar_t *value)
{
    size_t bytes = (wcslen(value) + 1) * sizeof(wchar_t);
    wchar_t *result = malloc(bytes);
    if (result) memcpy(result, value, bytes);
    return result;
}
wchar_t *swp_absolute(const sw_package *package, const wchar_t *relative)
{
    size_t n = wcslen(package->root), r = wcslen(relative), i;
    wchar_t *result = malloc((n + r + 2) * sizeof(wchar_t));
    if (!result) return NULL;
    memcpy(result, package->root, n * sizeof(wchar_t));
    if (r) {
#ifdef _WIN32
        result[n++] = L'\\';
#else
        result[n++] = L'/';
#endif
    }
    for (i = 0; i <= r; ++i) {
        result[n+i] = relative[i];
#ifdef _WIN32
        if (result[n+i] == L'/') result[n+i] = L'\\';
#endif
    }
    return result;
}
size_t swp_find(const sw_package *p, const wchar_t *name)
{
    size_t low = 0, high = p->count;
    while (low < high) {
        size_t middle = low + (high - low) / 2;
        if (swp_fold_compare(p->files[middle].path, name) < 0) low = middle + 1;
        else high = middle;
    }
    return low;
}
int swp_directory(const sw_package *p, const wchar_t *name)
{
    wchar_t prefix[SW_PACKAGE_MAX_RELATIVE];
    size_t n = wcslen(name), index;
    if (!n) return 1;
    if (n + 1 >= SW_PACKAGE_MAX_RELATIVE) return 0;
    memcpy(prefix, name, n * sizeof(wchar_t));prefix[n] = L'/';prefix[n+1] = 0;
    index = swp_find(p, prefix);
    return index < p->count && !wcsncmp(p->files[index].path, prefix, n+1);
}
int swp_child(const wchar_t *parent, const wchar_t *name, wchar_t *result)
{
    size_t a = wcslen(parent), b = wcslen(name);
    if (a + b + (a ? 1 : 0) >= SW_PACKAGE_MAX_RELATIVE) return 0;
    memcpy(result, parent, a * sizeof(wchar_t));
    if (a) result[a++] = L'/';
    memcpy(result+a, name, (b+1) * sizeof(wchar_t));
    return swp_relative(result);
}
