/* SPDX-License-Identifier: Apache-2.0 */
#include <Python.h>
#include <stdio.h>
#include <string.h>
#include "package.h"
#include "startup.h"
#include "fixture.h"

int main(int argc, char **argv)
{
    size_t index;
    if (argc != 2) return 2;
    for (index = 0; index < sizeof(fixture_names) / sizeof(fixture_names[0]); ++index) {
        if (strcmp(argv[1], fixture_names[index]) == 0) break;
    }
    if (index == sizeof(fixture_names) / sizeof(fixture_names[0]) || Py_IsInitialized()) return 3;
    sw_package *package = NULL;
    sw_package_result result = sw_package_open(fixture_roots[index], &fixture_file, 1, &package);
    if (index != 0) {
        if (result != fixture_errors[index] || package != NULL || Py_IsInitialized()) return 4;
    } else {
        if (result != SW_PACKAGE_OK || package == NULL) return 5;
        wchar_t archive[SW_PACKAGE_MAX_ROOT + SW_PACKAGE_MAX_RELATIVE + 2];
        if (sw_package_resolve(package, L"stdlib.zip", SW_PACKAGE_FILE, archive,
                               sizeof(archive) / sizeof(archive[0])) != SW_PACKAGE_OK) return 6;
        const wchar_t *search[] = {archive};
        sw_python_paths paths = {
#define SW_ASSIGN_ROOT(name) .name = fixture_roots[0],
            SW_PYTHON_PATH_FIELDS(SW_ASSIGN_ROOT)
#undef SW_ASSIGN_ROOT
            .search_path_count = 1, .search_paths = search
        };
        paths.program_name = paths.executable = paths.base_executable = fixture_executable;
        if (sw_python_start(&paths) != SW_PYTHON_OK) return 7;
        int checked = PyRun_SimpleString(fixture_checks);
        sw_python_result stopped = sw_python_stop();
        sw_package_close(package);
        if (checked != 0 || stopped != SW_PYTHON_OK || Py_IsInitialized()) return 8;
    }
    puts("SYNCWATCH_BOOTSTRAP_STDLIB_OK");
    return 0;
}
