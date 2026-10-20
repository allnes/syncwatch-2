/* SPDX-License-Identifier: Apache-2.0 */
#include <Python.h>
#include <locale.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include "startup.h"
#include "fixture.h"
#ifdef MS_WINDOWS
#include <windows.h>
#else
#include <pthread.h>
#endif

#define CHECK(expression) do { if (!(expression)) { \
    fprintf(stderr, "Native startup assertion at line %d\n", __LINE__); return 1; } } while (0)

static void sentinel(int number) { (void)number; }
static sw_python_result thread_result;
#ifdef MS_WINDOWS
static DWORD WINAPI stop_elsewhere(LPVOID unused)
#else
static void *stop_elsewhere(void *unused)
#endif
{
    (void)unused;
    thread_result = sw_python_stop();
    return 0;
}

static int wrong_thread(void)
{
#ifdef MS_WINDOWS
    HANDLE thread = CreateThread(NULL, 0, stop_elsewhere, NULL, 0, NULL);
    CHECK(thread != NULL);
    CHECK(WaitForSingleObject(thread, 10000) == WAIT_OBJECT_0);
    CHECK(CloseHandle(thread));
#else
    pthread_t thread;
    CHECK(pthread_create(&thread, NULL, stop_elsewhere, NULL) == 0);
    CHECK(pthread_join(thread, NULL) == 0);
#endif
    CHECK(thread_result == SW_PYTHON_WRONG_THREAD && Py_IsInitialized());
    return 0;
}

static int invalid_paths(void)
{
    sw_python_paths changed = fixture_paths;
    const wchar_t *invalid[] = { L"relative" };
    wchar_t oversized[SW_PYTHON_MAX_PATH_CHARS + 1];
    size_t index;
    CHECK(sw_python_stop() == SW_PYTHON_INVALID_STATE);
    CHECK(sw_python_start(NULL) == SW_PYTHON_INVALID_PATHS);
#define SW_CHECK_FIELD(name) \
    changed.name = NULL; CHECK(sw_python_start(&changed) == SW_PYTHON_INVALID_PATHS); \
    changed.name = L"relative"; CHECK(sw_python_start(&changed) == SW_PYTHON_INVALID_PATHS); \
    changed.name = L""; CHECK(sw_python_start(&changed) == SW_PYTHON_INVALID_PATHS); \
    changed = fixture_paths;
    SW_PYTHON_PATH_FIELDS(SW_CHECK_FIELD)
#undef SW_CHECK_FIELD
    changed.search_path_count = 0;
    CHECK(sw_python_start(&changed) == SW_PYTHON_INVALID_PATHS);
    changed.search_path_count = SW_PYTHON_MAX_SEARCH_PATHS + 1;
    CHECK(sw_python_start(&changed) == SW_PYTHON_INVALID_PATHS);
    changed = fixture_paths;
    changed.search_paths = NULL;
    CHECK(sw_python_start(&changed) == SW_PYTHON_INVALID_PATHS);
    changed.search_paths = invalid;
    changed.search_path_count = 1;
    CHECK(sw_python_start(&changed) == SW_PYTHON_INVALID_PATHS);
    invalid[0] = NULL;
    CHECK(sw_python_start(&changed) == SW_PYTHON_INVALID_PATHS);
    for (index = 0; index < SW_PYTHON_MAX_PATH_CHARS; ++index) oversized[index] = L'/';
    oversized[SW_PYTHON_MAX_PATH_CHARS] = L'\0';
    changed = fixture_paths;
    changed.home = oversized;
    CHECK(sw_python_start(&changed) == SW_PYTHON_INVALID_PATHS);
    CHECK(!Py_IsInitialized());
    return 0;
}

int main(int argc, char **argv)
{
    sw_python_paths paths = fixture_paths;
    sw_python_result final_result;
    int script_result;
    CHECK(argc == 2);
    CHECK(strncmp(Py_GetVersion(), PY_VERSION " ", strlen(PY_VERSION) + 1) == 0);
    if (strcmp(argv[1], "foreign") == 0) {
        PyConfig config;
        PyStatus status;
        PyConfig_InitIsolatedConfig(&config);
        status = PyConfig_SetString(&config, &config.home, paths.home);
        CHECK(!PyStatus_Exception(status));
        status = Py_InitializeFromConfig(&config);
        PyConfig_Clear(&config);
        CHECK(!PyStatus_Exception(status) && Py_IsInitialized());
        CHECK(sw_python_start(&paths) == SW_PYTHON_INVALID_STATE);
        CHECK(sw_python_stop() == SW_PYTHON_INVALID_STATE && Py_IsInitialized());
        CHECK(Py_FinalizeEx() == 0);
        CHECK(sw_python_start(&paths) == SW_PYTHON_INVALID_STATE);
    } else if (strcmp(argv[1], "init-failure") == 0) {
        const wchar_t *missing[] = { fixture_missing };
        paths.search_paths = missing;
        paths.search_path_count = 1;
        CHECK(sw_python_start(&paths) == SW_PYTHON_INITIALIZE_FAILED);
        CHECK(sw_python_start(&fixture_paths) == SW_PYTHON_INVALID_STATE);
        CHECK(sw_python_stop() == SW_PYTHON_INVALID_STATE);
    } else if (strcmp(argv[1], "adjacent-config") == 0) {
        sw_python_result result;
        paths.program_name = fixture_adjacent;
        paths.executable = fixture_adjacent;
        paths.base_executable = fixture_adjacent;
        result = sw_python_start(&paths);
        CHECK(result == SW_PYTHON_OK || result == SW_PYTHON_PATH_POLICY_FAILED);
        if (result == SW_PYTHON_OK) CHECK(sw_python_stop() == SW_PYTHON_OK);
        CHECK(!Py_IsInitialized());
        CHECK(sw_python_start(&paths) == SW_PYTHON_INVALID_STATE);
    } else {
        CHECK(strcmp(argv[1], "success") == 0 || strcmp(argv[1], "wrong-thread") == 0 ||
              strcmp(argv[1], "script-error") == 0 || strcmp(argv[1], "finalize-error") == 0);
        CHECK(invalid_paths() == 0);
        CHECK(setlocale(LC_CTYPE, "C") != NULL);
        CHECK(signal(SIGINT, sentinel) != SIG_ERR);
        CHECK(sw_python_start(&paths) == SW_PYTHON_OK && Py_IsInitialized());
        CHECK(sw_python_start(&paths) == SW_PYTHON_INVALID_STATE && Py_IsInitialized());
        CHECK(strcmp(setlocale(LC_CTYPE, NULL), "C") == 0);
        CHECK(signal(SIGINT, sentinel) == sentinel);
        script_result = PyRun_SimpleString(fixture_checks);
        if (script_result != 0) { (void)sw_python_stop(); return 1; }
        if (strcmp(argv[1], "wrong-thread") == 0) CHECK(wrong_thread() == 0);
        if (strcmp(argv[1], "script-error") == 0)
            CHECK(PyRun_SimpleString("raise RuntimeError('Controlled fixture exception')") != 0);
        if (strcmp(argv[1], "finalize-error") == 0)
            CHECK(PyRun_SimpleString("import sys\nclass Broken:\n def flush(self): raise OSError('Controlled flush failure')\nsys.stdout=Broken()\n") == 0);
        final_result = sw_python_stop();
        CHECK(final_result == (strcmp(argv[1], "finalize-error") == 0 ? SW_PYTHON_FINALIZE_FAILED : SW_PYTHON_OK));
        CHECK(!Py_IsInitialized());
        CHECK(signal(SIGINT, SIG_DFL) == sentinel);
        CHECK(sw_python_stop() == SW_PYTHON_INVALID_STATE);
        CHECK(sw_python_start(&paths) == SW_PYTHON_INVALID_STATE);
    }
    puts("SYNCWATCH_NATIVE_STARTUP_OK");
    return 0;
}
