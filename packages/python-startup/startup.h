/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SYNCWATCH_PYTHON_STARTUP_H
#define SYNCWATCH_PYTHON_STARTUP_H

#include <stddef.h>
#include <wchar.h>
#include "policy.generated.h"

#define SW_PYTHON_MAX_PATH_CHARS 32768
#define SW_PYTHON_MAX_SEARCH_PATHS 16

typedef struct {
#define SW_PATH_FIELD(name) const wchar_t *name;
    SW_PYTHON_PATH_FIELDS(SW_PATH_FIELD)
#undef SW_PATH_FIELD
    size_t search_path_count;
    const wchar_t *const *search_paths;
} sw_python_paths;

typedef enum {
    SW_PYTHON_OK = 0,
    SW_PYTHON_INVALID_PATHS,
    SW_PYTHON_INVALID_STATE,
    SW_PYTHON_WRONG_THREAD,
    SW_PYTHON_PREINITIALIZE_FAILED,
    SW_PYTHON_CONFIGURE_FAILED,
    SW_PYTHON_INITIALIZE_FAILED,
    SW_PYTHON_PATH_POLICY_FAILED,
    SW_PYTHON_FINALIZE_FAILED
} sw_python_result;

/* Dedicated helper process only. Calls must be serialized by the owner.
 * Paths must already be verified package paths, absolute and NUL-terminated.
 * This API validates shape/bounds and observed interpreter paths, not filesystem
 * ownership or symlink safety. Reject foreign package configuration files before use.
 * Invalid input leaves startup untouched. Once preinitialization is attempted,
 * this process cannot start again. Dispose of the process after any failure.
 * Stop on the starting thread with its main interpreter/GIL still active.
 * No other code may initialize/finalize Python or replace that interpreter.
 */
sw_python_result sw_python_start(const sw_python_paths *paths);
sw_python_result sw_python_stop(void);

#endif
