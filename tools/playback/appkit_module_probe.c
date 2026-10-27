/* SPDX-License-Identifier: Apache-2.0 */
#include "../../packages/playback-native/src/vlc_api.h"
#include "../../packages/playback-native/include/syncwatch_playback.h"
#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>

static void *repeat(void *path) {
    for (unsigned i = 0; i < 32; ++i)
        if (!sw_library_prepare_output(path, SW_OUTPUT_APPKIT)) return path;
    return NULL;
}

int main(int argc, char **argv) {
    if (argc != 7) return 1;
    if (sw_library_prepare_output(argv[1], SW_OUTPUT_APPKIT)) return 2;
    if (!sw_library_prepare_output(argv[2], SW_OUTPUT_APPKIT)) return 3;
    void *module = dlopen(argv[3], RTLD_NOW | RTLD_LOCAL | RTLD_NOLOAD);
    if (!module) return 4;
    void *entry = dlsym(module, "fixture_identity");
    if (!entry || dlclose(module)) return 5;
    pthread_t threads[4];
    for (unsigned i = 0; i < 4; ++i)
        if (pthread_create(&threads[i], NULL, repeat, i % 2 ? argv[4] : argv[2])) return 6;
    for (unsigned i = 0; i < 4; ++i) {
        void *failure;
        if (pthread_join(threads[i], &failure) || failure) return 7;
    }
    module = dlopen(argv[3], RTLD_NOW | RTLD_LOCAL | RTLD_NOLOAD);
    if (!module || dlsym(module, "fixture_identity") != entry || dlclose(module)) return 8;
    if (sw_library_prepare_output(argv[5], SW_OUTPUT_APPKIT)) return 9;
    void *ordinary = dlopen(argv[6], RTLD_NOW | RTLD_LOCAL);
    if (!ordinary || dlclose(ordinary)) return 10;
    ordinary = dlopen(argv[6], RTLD_NOW | RTLD_LOCAL | RTLD_NOLOAD);
    if (ordinary) { dlclose(ordinary); return 11; }
    puts("SYNCWATCH_APPKIT_MODULE_LIFETIME_OK missing/retry/concurrent/symlink/reopen/foreign/unrelated unload");
    return 0;
}
