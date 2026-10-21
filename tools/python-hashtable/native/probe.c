/* First-party bounded standalone test ports, not a Python embedding ABI. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
#include "fixture.h"
#include "corpus.h"
#ifdef NDEBUG
#error "This fixture requires assertions"
#endif

static uint64_t keys[FIXTURE_KEYS], copies[FIXTURE_KEYS];
static unsigned int values[FIXTURE_KEYS];
static void *allocations[1024];
static size_t live, calls, fail_at, failures, keys_destroyed, values_destroyed;

static void *tracked_malloc(size_t size)
{
    void *p;
    calls++;
    if (calls == fail_at) { failures++; return NULL; }
    p = malloc(size);
    assert(p != NULL && live < 1024);
    allocations[live++] = p;
    return p;
}

static void tracked_free(void *p)
{
    size_t n;
    assert(p != NULL);
    for (n = 0; n < live && allocations[n] != p; n++) { }
    assert(n < live);
    allocations[n] = allocations[--live];
    free(p);
}

static void key_destroy(void *p) { assert(p != NULL); keys_destroyed++; }
static void value_destroy(void *p) { (void)p; values_destroyed++; }
static Py_uhash_t collision_hash(const void *key) { (void)key; return 0; }
static Py_uhash_t integer_hash(const void *key) { return (Py_uhash_t)(*(const uint64_t *)key * UINT64_C(2654435761)); }
static int integer_equal(const void *a, const void *b) { return *(const uint64_t *)a == *(const uint64_t *)b; }

static void word(unsigned int value)
{
    unsigned char out[4];
    out[0] = (unsigned char)((value >> 24) & 255u);
    out[1] = (unsigned char)((value >> 16) & 255u);
    out[2] = (unsigned char)((value >> 8) & 255u);
    out[3] = (unsigned char)(value & 255u);
    assert(fwrite(out, 1, 4, stdout) == 4);
}

struct visit { size_t count; unsigned int sum; };
static int visit(_Py_hashtable_t *table, const void *key, const void *value, void *data)
{
    struct visit *state = data;
    const uint64_t k = *(const uint64_t *)key;
    assert(k < FIXTURE_KEYS && _Py_hashtable_get_entry(table, key) != NULL);
    assert(value == (k ? &values[k] : NULL));
    state->count++;
    if (value) state->sum += *(const unsigned int *)value;
    return 0;
}

static int stop(_Py_hashtable_t *table, const void *key, const void *value, void *data)
{
    size_t *count = data;
    (void)table; (void)key; (void)value;
    (*count)++;
    return 73;
}

static unsigned int inspect(_Py_hashtable_t *table, size_t expected)
{
    struct visit state = {0, 0};
    size_t stopped = 0;
    assert(_Py_hashtable_len(table) == expected);
    assert(table->nbuckets >= 16 && (table->nbuckets & (table->nbuckets - 1)) == 0);
    assert(_Py_hashtable_size(table) >= sizeof(*table) + expected * sizeof(_Py_hashtable_entry_t));
    assert(_Py_hashtable_foreach(table, visit, &state) == 0 && state.count == expected);
    assert(_Py_hashtable_foreach(table, stop, &stopped) == (expected ? 73 : 0));
    assert(stopped == (expected ? 1u : 0u));
    return state.sum;
}

static _Py_hashtable_t *new_table(unsigned int mode)
{
    _Py_hashtable_allocator_t allocator = {tracked_malloc, tracked_free};
    return _Py_hashtable_new_full(mode == 0 ? collision_hash : mode == 3 ? _Py_hashtable_hash_ptr : integer_hash,
        mode == 2 ? integer_equal : _Py_hashtable_compare_direct, key_destroy, value_destroy, &allocator);
}

static void model_run(unsigned int mode)
{
    _Py_hashtable_t *table = new_table(mode);
    size_t length = 0, removed = 0, step;
    assert(table != NULL);
    for (step = 0; step < FIXTURE_OPS; step++) {
        unsigned int op = fixture_ops[step][0], key = fixture_ops[step][1], value = 0, found;
        void *query = mode == 2 ? &copies[key] : &keys[key];
        _Py_hashtable_entry_t *entry = _Py_hashtable_get_entry(table, query);
        found = entry != NULL;
        if (entry && entry->value) value = *(unsigned int *)entry->value;
        assert(_Py_hashtable_get(table, query) == (entry ? entry->value : NULL));
        if (op == 0) {
            if (!found) {
                assert(_Py_hashtable_set(table, &keys[key], key ? &values[key] : NULL) == 0);
                length++;
            }
            found = 1; value = key ? values[key] : 0;
        }
        else if (op == 2) {
            void *stolen = _Py_hashtable_steal(table, query);
            assert(stolen == (found ? (key ? &values[key] : NULL) : NULL));
            if (found) length--;
            assert(_Py_hashtable_get_entry(table, query) == NULL);
        }
        else if (op == 3) {
            removed += length;
            _Py_hashtable_clear(table); length = 0; found = 0; value = 0;
        }
        word(mode); word(op); word(key); word(found); word(value);
        word((unsigned int)length); word(inspect(table, length));
    }
    removed += length;
    _Py_hashtable_destroy(table);
    assert(live == 0 && keys_destroyed == removed && values_destroyed == removed);
    keys_destroyed = values_destroyed = 0;
}

static size_t allocation_run(size_t position)
{
    _Py_hashtable_t *table;
    unsigned int key;
    size_t length = 0, total;
    assert(live == 0);
    calls = failures = 0; fail_at = position;
    table = new_table(0);
    if (!table) {
        assert(live == 0 && failures == 1);
        table = new_table(0); assert(table != NULL);
    }
    for (key = 0; key < 200; key++) {
        int result = _Py_hashtable_set(table, &keys[key], key ? &values[key] : NULL);
        if (result < 0) {
            assert(_Py_hashtable_get_entry(table, &keys[key]) == NULL);
            (void)inspect(table, length);
            assert(_Py_hashtable_set(table, &keys[key], key ? &values[key] : NULL) == 0);
        }
        length++;
        (void)inspect(table, length);
    }
    for (key = 0; key < 150; key++) {
        assert(_Py_hashtable_get_entry(table, &keys[key]) != NULL);
        assert(_Py_hashtable_steal(table, &keys[key]) == (key ? &values[key] : NULL));
        length--;
        (void)inspect(table, length);
    }
    _Py_hashtable_clear(table); (void)inspect(table, 0);
    for (key = 0; key < 16; key++) {
        if (_Py_hashtable_set(table, &keys[key], key ? &values[key] : NULL) < 0) {
            (void)inspect(table, key);
            assert(_Py_hashtable_set(table, &keys[key], key ? &values[key] : NULL) == 0);
        }
    }
    (void)inspect(table, 16);
    total = calls;
    _Py_hashtable_destroy(table);
    assert(live == 0 && failures == (position ? 1u : 0u));
    assert(keys_destroyed == 66 && values_destroyed == 66);
    keys_destroyed = values_destroyed = 0;
    return total;
}

int main(void)
{
    unsigned int n;
    size_t count, position;
    _Py_hashtable_t *defaults;
#ifdef _WIN32
    assert(_setmode(_fileno(stdout), _O_BINARY) != -1);
#endif
    _Static_assert(sizeof(void *) == 8 && sizeof(size_t) == 8, "64-bit fixture only");
    for (n = 0; n < FIXTURE_KEYS; n++) { keys[n] = copies[n] = n; values[n] = n + 1000; }
    defaults = _Py_hashtable_new(_Py_hashtable_hash_ptr, _Py_hashtable_compare_direct);
    assert(defaults != NULL && _Py_hashtable_set(defaults, &keys[0], NULL) == 0);
    assert(_Py_hashtable_get_entry(defaults, &keys[0]) != NULL && _Py_hashtable_get(defaults, &keys[0]) == NULL);
    assert(_Py_hashtable_set(defaults, NULL, &values[0]) == 0);
    assert(_Py_hashtable_get(defaults, NULL) == &values[0]);
    assert(_Py_hashtable_steal(defaults, NULL) == &values[0]);
    assert(_Py_hashtable_get_entry(defaults, NULL) == NULL);
    _Py_hashtable_destroy(defaults);
    assert(fwrite("SWHT0001", 1, 8, stdout) == 8);
    for (n = 0; n < FIXTURE_PROFILES; n++) model_run(n);
    count = allocation_run(0); assert(count > 200 && count < 512);
    for (position = 1; position <= count; position++) (void)allocation_run(position);
    assert(fwrite("FAILURE_SWEEP_OK\n", 1, sizeof("FAILURE_SWEEP_OK\n") - 1, stdout) == sizeof("FAILURE_SWEEP_OK\n") - 1);
    return ferror(stdout) ? 1 : 0;
}
