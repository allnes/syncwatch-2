/* SPDX-License-Identifier: Apache-2.0 */
#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>
#include "startup.h"
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

static wchar_t paths[4][SW_PYTHON_MAX_PATH_CHARS];

static int run(int argc, wchar_t **argv)
{
    const wchar_t *search[4];
    sw_python_paths config;
    int result;
    if (argc != 2) return 64;
#ifdef _WIN32
    if (_setmode(_fileno(stdin), _O_BINARY) == -1 || _setmode(_fileno(stdout), _O_BINARY) == -1) return 70;
#define CORE L"/bin"
#define STDLIB L"/bin/python312.zip"
#else
#define CORE L"/lib"
#define STDLIB L"/lib/python312.zip"
#endif
    if (swprintf(paths[0], SW_PYTHON_MAX_PATH_CHARS, L"%ls/app", argv[1]) < 0 ||
        swprintf(paths[1], SW_PYTHON_MAX_PATH_CHARS, L"%ls/python", argv[1]) < 0 ||
        swprintf(paths[2], SW_PYTHON_MAX_PATH_CHARS, L"%ls" STDLIB, argv[1]) < 0 ||
        swprintf(paths[3], SW_PYTHON_MAX_PATH_CHARS, L"%ls" CORE, argv[1]) < 0) return 64;
    search[0] = paths[0]; search[1] = paths[1]; search[2] = paths[2]; search[3] = paths[3];
    config.home = config.prefix = config.base_prefix = config.exec_prefix = config.base_exec_prefix = argv[1];
    config.program_name = config.executable = config.base_executable = argv[0];
    config.search_path_count = 4;
    config.search_paths = search;
    if (sw_python_start(&config) != SW_PYTHON_OK) return 70;
    result = PyRun_SimpleString("from syncwatch_bridge.main import main\nmain()\n");
    if (sw_python_stop() != SW_PYTHON_OK) return 70;
    return result == 0 ? 0 : 70;
}

#ifdef _WIN32
int wmain(int argc, wchar_t **argv) { return run(argc, argv); }
#else
/* Decode the OS UTF-8 arguments independently of ambient locale/PYTHONUTF8. */
static wchar_t *utf8(const char *input)
{
    const unsigned char *p = (const unsigned char *)input;
    size_t length = 0;
    wchar_t *output = calloc(SW_PYTHON_MAX_PATH_CHARS, sizeof(wchar_t));
    if (output == NULL) return NULL;
    while (*p) {
        unsigned int value = *p++, minimum = 0;
        int count = 0;
        if (value >= 0xc2 && value <= 0xdf) { count = 1; value &= 31; minimum = 0x80; }
        else if (value >= 0xe0 && value <= 0xef) { count = 2; value &= 15; minimum = 0x800; }
        else if (value >= 0xf0 && value <= 0xf4) { count = 3; value &= 7; minimum = 0x10000; }
        else if (value >= 0x80) goto invalid;
        while (count--) {
            if ((*p & 0xc0) != 0x80) goto invalid;
            value = (value << 6) | (*p++ & 63);
        }
        if (value < minimum || value > 0x10ffff || (value >= 0xd800 && value <= 0xdfff) ||
            length >= SW_PYTHON_MAX_PATH_CHARS - 1) goto invalid;
        output[length++] = (wchar_t)value;
    }
    return output;
invalid:
    free(output);
    return NULL;
}

int main(int argc, char **argv)
{
    wchar_t *arguments[2];
    int result;
    if (argc != 2) return 64;
    arguments[0] = utf8(argv[0]); arguments[1] = utf8(argv[1]);
    if (arguments[0] == NULL || arguments[1] == NULL) result = 64;
    else result = run(argc, arguments);
    free(arguments[0]); free(arguments[1]);
    return result;
}
#endif
