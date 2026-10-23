#ifndef SYNCWATCH_VLC_PROBE_COMMON_H
#define SYNCWATCH_VLC_PROBE_COMMON_H
/* SPDX-License-Identifier: Apache-2.0
 * Exercise the actual libVLC C API using decoded video and audio observations.
 * Memory callbacks establish decoder behavior, not physical output acceptance.
 */
#define _GNU_SOURCE
#define _DARWIN_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#include <vlc/vlc.h>
#include <math.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef SW_VLC_REVISION
#error "The native media probe requires its exact source revision"
#endif
#include "owned_libraries.h"
#ifdef _WIN32
static inline void delay(void) { Sleep(10); }
static inline uint64_t milliseconds(void) { return GetTickCount64(); }
#else
#include <time.h>
static inline void delay(void) { const struct timespec t = {0, 10000000}; nanosleep(&t, NULL); }
static inline uint64_t milliseconds(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000 + (uint64_t)t.tv_nsec / 1000000;
}
#endif


enum { WIDTH = 320, HEIGHT = 180, PITCH = WIDTH * 4 };
struct observations {
    _Alignas(32) unsigned char pixels[PITCH * HEIGHT];
    atomic_uint frames, audio_blocks, luminance;
    atomic_uint audio_peak, audio_samples, positive_crossings;
    atomic_uint hardware_sessions, hardware_errors;
    atomic_uint minimum_luminance;
    int previous_sample;
};

static inline void observe_log(void *opaque, int level, const libvlc_log_t *context,
                        const char *format, va_list arguments) {
    struct observations *o = opaque;
    const char *module = NULL;
    char text[1024];
    libvlc_log_get_context(context, &module, NULL, NULL);
    if (level == LIBVLC_ERROR) {
        va_list copy;
        va_copy(copy, arguments);
        vsnprintf(text, sizeof(text), format, copy);
        va_end(copy);
        fprintf(stderr, "native decoder error (%s): %s\n", module ? module : "unknown", text);
    }
    if (!module || strcmp(module, "videotoolbox") != 0) return;
    vsnprintf(text, sizeof(text), format, arguments);
    if (strstr(text, "Using Video Toolbox to decode")) atomic_fetch_add(&o->hardware_sessions, 1);
    if (level == LIBVLC_ERROR) atomic_fetch_add(&o->hardware_errors, 1);
}

static inline void *lock_video(void *opaque, void **planes) {
    struct observations *o = opaque;
    planes[0] = o->pixels;
    return NULL;
}

static inline void display_video(void *opaque, void *picture) {
    struct observations *o = opaque;
    (void)picture;
    unsigned luminance = o->pixels[(HEIGHT / 2) * PITCH + WIDTH * 2];
    atomic_store(&o->luminance, luminance);
    unsigned minimum = atomic_load(&o->minimum_luminance);
    while (luminance < minimum && !atomic_compare_exchange_weak(&o->minimum_luminance, &minimum, luminance)) {}
    atomic_fetch_add(&o->frames, 1);
}

static inline void play_audio(void *opaque, const void *samples, unsigned count, int64_t pts) {
    struct observations *o = opaque;
    const int16_t *pcm = samples;
    unsigned peak = 0;
    (void)pts;
    for (unsigned i = 0; i < count * 2; ++i) {
        unsigned value = (unsigned)abs(pcm[i]);
        if (value > peak) peak = value;
    }
    for (unsigned i = 0; i < count; ++i) {
        int value = pcm[i * 2];
        if (o->previous_sample <= 0 && value > 0) atomic_fetch_add(&o->positive_crossings, 1);
        o->previous_sample = value;
    }
    atomic_fetch_add(&o->audio_samples, count);
    if (peak > atomic_load(&o->audio_peak)) atomic_store(&o->audio_peak, peak);
    atomic_fetch_add(&o->audio_blocks, 1);
}

static inline int wait_state(libvlc_media_player_t *player, libvlc_state_t desired) {
    uint64_t deadline = milliseconds() + 10000;
    while (milliseconds() < deadline) {
        if (libvlc_media_player_get_state(player) == desired) return 1;
        if (libvlc_media_player_get_state(player) == libvlc_Error) return 0;
        delay();
    }
    return 0;
}

static inline int wait_frames(struct observations *o, unsigned count, unsigned luminance) {
    uint64_t deadline = milliseconds() + 10000;
    while (milliseconds() < deadline) {
        if (atomic_load(&o->frames) >= count && atomic_load(&o->luminance) >= luminance) return 1;
        delay();
    }
    return 0;
}

static inline int wait_audio(struct observations *o) {
    uint64_t deadline = milliseconds() + 10000;
    while (milliseconds() < deadline) {
        if (atomic_load(&o->audio_samples) >= 8820 && atomic_load(&o->audio_peak) >= 6500) return 1;
        delay();
    }
    fprintf(stderr, "audio observations: blocks=%u samples=%u peak=%u\n",
        atomic_load(&o->audio_blocks), atomic_load(&o->audio_samples), atomic_load(&o->audio_peak));
    return 0;
}

static inline int wait_low_frames(struct observations *o, unsigned count) {
    uint64_t deadline = milliseconds() + 10000;
    while (milliseconds() < deadline) {
        if (atomic_load(&o->frames) >= count && atomic_load(&o->luminance) < 90) return 1;
        delay();
    }
    fprintf(stderr, "backward observations: minimum=%u current=%u frames=%u expected-count=%u\n",
        atomic_load(&o->minimum_luminance), atomic_load(&o->luminance), atomic_load(&o->frames), count);
    return 0;
}

#define REQUIRE(condition, message) do { if (!(condition)) { \
    fprintf(stderr, "libVLC probe: %s\n", message); result = 1; goto cleanup; } } while (0)


#endif
