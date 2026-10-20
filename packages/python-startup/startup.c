/* SPDX-License-Identifier: Apache-2.0 */
#include <Python.h>
#include "startup.h"

#if PY_VERSION_HEX < 0x030C0000 || PY_VERSION_HEX >= 0x04000000
#error CPython 3.12 or newer within 3.x is required
#endif
#ifdef Py_GIL_DISABLED
#error The startup lifecycle requires a GIL-enabled interpreter
#endif

typedef enum { FRESH, STARTING, ACTIVE, TERMINAL } phase;
static phase state = FRESH;
static unsigned long owner_thread;
static PyThreadState *owner_interpreter;

static int absolute_path(const wchar_t *path)
{
    size_t length = 0;
    if (path == NULL) return 0;
    while (length < SW_PYTHON_MAX_PATH_CHARS && path[length] != L'\0') ++length;
    if (length == 0 || length == SW_PYTHON_MAX_PATH_CHARS) return 0;
#ifdef MS_WINDOWS
    return length >= 3 && ((path[0] >= L'A' && path[0] <= L'Z') ||
                          (path[0] >= L'a' && path[0] <= L'z')) &&
           path[1] == L':' && (path[2] == L'\\' || path[2] == L'/');
#else
    return path[0] == L'/';
#endif
}

static int valid_paths(const sw_python_paths *paths)
{
    size_t index;
    if (paths == NULL || paths->search_paths == NULL || paths->search_path_count == 0 ||
        paths->search_path_count > SW_PYTHON_MAX_SEARCH_PATHS) return 0;
#define SW_VALIDATE_PATH(name) if (!absolute_path(paths->name)) return 0;
    SW_PYTHON_PATH_FIELDS(SW_VALIDATE_PATH)
#undef SW_VALIDATE_PATH
    for (index = 0; index < paths->search_path_count; ++index) {
        if (!absolute_path(paths->search_paths[index])) return 0;
    }
    return 1;
}

static int same_path(PyObject *observed, const wchar_t *expected)
{
    PyObject *text;
    int result;
    if (observed == NULL || !PyUnicode_Check(observed)) return 0;
    text = PyUnicode_FromWideChar(expected, -1);
    if (text == NULL) return 0;
    result = PyObject_RichCompareBool(observed, text, Py_EQ);
    Py_DECREF(text);
    return result == 1;
}

static int observed_paths(const sw_python_paths *paths)
{
    size_t index;
    PyObject *search = PySys_GetObject("path");
#define SW_OBSERVED(name, key) if (!same_path(PySys_GetObject(key), paths->name)) return 0;
    SW_OBSERVED(executable, "executable")
    SW_OBSERVED(base_executable, "_base_executable")
    SW_OBSERVED(prefix, "prefix")
    SW_OBSERVED(base_prefix, "base_prefix")
    SW_OBSERVED(exec_prefix, "exec_prefix")
    SW_OBSERVED(base_exec_prefix, "base_exec_prefix")
    SW_OBSERVED(stdlib_dir, "_stdlib_dir")
#undef SW_OBSERVED
    if (search == NULL || !PyList_CheckExact(search) ||
        PyList_Size(search) != (Py_ssize_t)paths->search_path_count) return 0;
    for (index = 0; index < paths->search_path_count; ++index) {
        if (!same_path(PyList_GetItem(search, (Py_ssize_t)index), paths->search_paths[index])) return 0;
    }
    return 1;
}

sw_python_result sw_python_start(const sw_python_paths *paths)
{
    PyPreConfig preconfig;
    PyConfig config;
    PyStatus status;
    sw_python_result result = SW_PYTHON_CONFIGURE_FAILED;
    size_t index;
    if (state != FRESH) return SW_PYTHON_INVALID_STATE;
    if (Py_IsInitialized()) {
        state = TERMINAL;
        return SW_PYTHON_INVALID_STATE;
    }
    if (!valid_paths(paths)) return SW_PYTHON_INVALID_PATHS;
    state = STARTING;
    PyPreConfig_InitIsolatedConfig(&preconfig);
#define SW_PRECONFIG(name, value) preconfig.name = value;
    SW_PYTHON_PRECONFIG(SW_PRECONFIG)
#undef SW_PRECONFIG
    status = Py_PreInitialize(&preconfig);
    if (PyStatus_Exception(status)) {
        state = TERMINAL;
        return SW_PYTHON_PREINITIALIZE_FAILED;
    }
    PyConfig_InitIsolatedConfig(&config);
#define SW_CONFIG(name, value) config.name = value;
    SW_PYTHON_CONFIG(SW_CONFIG)
#undef SW_CONFIG
#define SW_SET_PATH(name) \
    status = PyConfig_SetString(&config, &config.name, paths->name); \
    if (PyStatus_Exception(status)) goto done;
    SW_PYTHON_PATH_FIELDS(SW_SET_PATH)
#undef SW_SET_PATH
    for (index = 0; index < paths->search_path_count; ++index) {
        status = PyWideStringList_Append(&config.module_search_paths, paths->search_paths[index]);
        if (PyStatus_Exception(status)) goto done;
    }
    status = Py_InitializeFromConfig(&config);
    if (PyStatus_Exception(status)) {
        result = SW_PYTHON_INITIALIZE_FAILED;
        goto done;
    }
    if (!observed_paths(paths)) {
        result = SW_PYTHON_PATH_POLICY_FAILED;
        goto done;
    }
    owner_thread = PyThread_get_thread_ident();
    owner_interpreter = PyThreadState_Get();
    result = SW_PYTHON_OK;
done:
    PyConfig_Clear(&config);
    if (result == SW_PYTHON_PATH_POLICY_FAILED) {
        PyErr_Clear();
        (void)Py_FinalizeEx();
    }
    state = result == SW_PYTHON_OK ? ACTIVE : TERMINAL;
    return result;
}

sw_python_result sw_python_stop(void)
{
    int result;
    if (state != ACTIVE) return SW_PYTHON_INVALID_STATE;
    if (PyThread_get_thread_ident() != owner_thread) return SW_PYTHON_WRONG_THREAD;
    if (!Py_IsInitialized() || !PyGILState_Check() || PyThreadState_Get() != owner_interpreter)
        return SW_PYTHON_INVALID_STATE;
    state = TERMINAL;
    owner_interpreter = NULL;
    result = Py_FinalizeEx();
    return result == 0 ? SW_PYTHON_OK : SW_PYTHON_FINALIZE_FAILED;
}
