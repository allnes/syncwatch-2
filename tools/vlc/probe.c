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
#ifdef _WIN32
#include <windows.h>
static void delay(void) { Sleep(10); }
static uint64_t milliseconds(void) { return GetTickCount64(); }
#else
#include <dlfcn.h>
#include <time.h>
static void delay(void) { const struct timespec t = {0, 10000000}; nanosleep(&t, NULL); }
static uint64_t milliseconds(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000 + (uint64_t)t.tv_nsec / 1000000;
}
#endif

static int owned_library(const char *expected) {
#ifdef _WIN32
    HMODULE module;
    char actual[32768], canonical[32768];
    if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            (const char *)(uintptr_t)&libvlc_get_version, &module) ||
            !GetModuleFileNameA(module, actual, sizeof(actual)) || !_fullpath(canonical, expected, sizeof(canonical))) return 0;
    for (char *p = actual; *p; ++p) if (*p == '/') *p = '\\';
    for (char *p = canonical; *p; ++p) if (*p == '/') *p = '\\';
    return _stricmp(actual, canonical) == 0;
#else
    Dl_info info;
    if (!dladdr((void *)(uintptr_t)&libvlc_get_version, &info)) return 0;
    char *actual = realpath(info.dli_fname, NULL), *canonical = realpath(expected, NULL);
    int matches = actual && canonical && strcmp(actual, canonical) == 0;
    free(actual); free(canonical);
    return matches;
#endif
}

enum { WIDTH = 320, HEIGHT = 180, PITCH = WIDTH * 4 };
struct observations {
    unsigned char pixels[PITCH * HEIGHT];
    atomic_uint frames, audio_blocks, luminance;
    atomic_uint audio_peak, audio_samples, positive_crossings;
    int previous_sample;
};

static void *lock_video(void *opaque, void **planes) {
    struct observations *o = opaque;
    planes[0] = o->pixels;
    return NULL;
}

static void unlock_video(void *opaque, void *picture, void *const *planes) {
    struct observations *o = opaque;
    (void)picture; (void)planes;
    atomic_store(&o->luminance, o->pixels[(HEIGHT / 2) * PITCH + WIDTH * 2]);
    atomic_fetch_add(&o->frames, 1);
}

static void play_audio(void *opaque, const void *samples, unsigned count, int64_t pts) {
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

static int wait_state(libvlc_media_player_t *player, libvlc_state_t desired) {
    uint64_t deadline = milliseconds() + 10000;
    while (milliseconds() < deadline) {
        if (libvlc_media_player_get_state(player) == desired) return 1;
        if (libvlc_media_player_get_state(player) == libvlc_Error) return 0;
        delay();
    }
    return 0;
}

static int wait_frames(struct observations *o, unsigned count, unsigned luminance) {
    uint64_t deadline = milliseconds() + 10000;
    while (milliseconds() < deadline) {
        if (atomic_load(&o->frames) >= count && atomic_load(&o->luminance) >= luminance) return 1;
        delay();
    }
    return 0;
}

static int wait_audio(struct observations *o) {
    uint64_t deadline = milliseconds() + 10000;
    while (milliseconds() < deadline) {
        if (atomic_load(&o->audio_samples) >= 8820 && atomic_load(&o->audio_peak) >= 6500) return 1;
        delay();
    }
    fprintf(stderr, "audio observations: blocks=%u samples=%u peak=%u\n",
        atomic_load(&o->audio_blocks), atomic_load(&o->audio_samples), atomic_load(&o->audio_peak));
    return 0;
}

#define REQUIRE(condition, message) do { if (!(condition)) { \
    fprintf(stderr, "libVLC probe: %s\n", message); result = 1; goto cleanup; } } while (0)

int main(int argc, char **argv) {
    const char *options[] = {"--ignore-config", "--no-plugins-cache", "--no-media-library",
        "--no-video-title-show", "--no-osd", "--no-sub-autodetect-file",
        "--avcodec-hw=none", "--vout=vmem", "--aout=amem", "--quiet"};
    struct observations observed = {0};
    libvlc_instance_t *instance = NULL;
    libvlc_media_t *media = NULL;
    libvlc_media_player_t *player = NULL;
    int result = 0;
    unsigned video_tracks = 0, audio_tracks = 0, paused_frames, paused_pixel, audio_frequency;
    uint32_t video_codec = 0, audio_codec = 0;
    libvlc_time_t paused_time;
    libvlc_media_track_t **tracks = NULL;
    uint64_t deadline;
    if (argc != 3) { fprintf(stderr, "usage: vlc-probe owned-media-path expected-library-path\n"); return 2; }
    REQUIRE(owned_library(argv[2]), "loaded library is not the owned relocated artifact");
    instance = libvlc_new((int)(sizeof(options) / sizeof(options[0])), options);
    REQUIRE(instance, "cannot create owned native instance");
    REQUIRE(strncmp(libvlc_get_version(), "3.0.24 ", 7) == 0, "unexpected native version");
    media = libvlc_media_new_path(instance, argv[1]);
    REQUIRE(media, "cannot create file media");
    REQUIRE(libvlc_media_parse_with_options(media, libvlc_media_parse_local, 10000) == 0,
            "metadata parse rejected");
    deadline = milliseconds() + 12000;
    while (libvlc_media_get_parsed_status(media) != libvlc_media_parsed_status_done && milliseconds() < deadline) delay();
    REQUIRE(libvlc_media_get_parsed_status(media) == libvlc_media_parsed_status_done, "metadata parse timed out");
    unsigned count = libvlc_media_tracks_get(media, &tracks);
    for (unsigned i = 0; i < count; ++i) {
        if (tracks[i]->i_type == libvlc_track_video && tracks[i]->video->i_width == WIDTH && tracks[i]->video->i_height == HEIGHT) {
            ++video_tracks; video_codec = tracks[i]->i_codec;
        }
        if (tracks[i]->i_type == libvlc_track_audio && tracks[i]->audio->i_channels == 2 && tracks[i]->audio->i_rate == 48000) {
            ++audio_tracks; audio_codec = tracks[i]->i_codec;
        }
    }
    libvlc_media_tracks_release(tracks, count); tracks = NULL;
    REQUIRE(video_tracks == 1 && audio_tracks == 1, "decoded metadata differs from fixture");
    REQUIRE(libvlc_media_get_duration(media) >= 3900 && libvlc_media_get_duration(media) <= 4100, "duration differs from fixture");
    player = libvlc_media_player_new_from_media(media);
    REQUIRE(player, "cannot create player");
    libvlc_video_set_callbacks(player, lock_video, unlock_video, NULL, &observed);
    libvlc_video_set_format(player, "RV32", WIDTH, HEIGHT, PITCH);
    libvlc_audio_set_callbacks(player, play_audio, NULL, NULL, NULL, NULL, &observed);
    libvlc_audio_set_format(player, "S16N", 44100, 2);
    REQUIRE(libvlc_media_player_play(player) == 0 && wait_state(player, libvlc_Playing), "play not observed");
    REQUIRE(wait_frames(&observed, 5, 1), "no decoded frames");
    REQUIRE(wait_audio(&observed), "no decoded PCM audio");
    audio_frequency = atomic_load(&observed.positive_crossings) * 44100 / atomic_load(&observed.audio_samples);
    REQUIRE(audio_frequency >= 430 && audio_frequency <= 450, "PCM rate conversion did not preserve the known tone");
    libvlc_media_player_set_pause(player, 1);
    REQUIRE(wait_state(player, libvlc_Paused), "pause not observed");
    // Let an already dispatched output callback finish before measuring pause.
    for (unsigned i = 0; i < 20; ++i) delay();
    paused_frames = atomic_load(&observed.frames);
    paused_pixel = atomic_load(&observed.luminance);
    paused_time = libvlc_media_player_get_time(player);
    for (unsigned i = 0; i < 20; ++i) delay();
    // A vout may redraw the same paused frame. Its pixels and media clock must
    // remain fixed; counting redraw callbacks would reject correct playback.
    REQUIRE(atomic_load(&observed.luminance) == paused_pixel &&
            libvlc_media_player_get_time(player) == paused_time, "media advanced while paused");
    libvlc_media_player_set_time(player, 2500);
    libvlc_media_player_set_pause(player, 0);
    REQUIRE(wait_state(player, libvlc_Playing), "resume not observed");
    REQUIRE(wait_frames(&observed, paused_frames + 3, 150), "seek not observed in actual decoded pixels");
    libvlc_media_player_stop(player);
    REQUIRE(wait_state(player, libvlc_Stopped), "stop not observed");
    atomic_store(&observed.frames, 0); atomic_store(&observed.luminance, 0);
    REQUIRE(libvlc_media_player_play(player) == 0 && wait_frames(&observed, 3, 1), "reload did not decode frames");
    REQUIRE(atomic_load(&observed.luminance) < 100, "reload did not restart actual media");
    libvlc_media_player_stop(player);
    printf("{\"version\":\"3.0.24\",\"videoTracks\":%u,\"audioTracks\":%u,"
           "\"audioPeak\":%u,\"resampledToneHz\":%u,\"videoCodec\":\"%08x\",\"audioCodec\":\"%08x\","
           "\"cases\":[\"metadata\",\"decodeVideo\",\"decodeAudio\","
           "\"play\",\"pause\",\"seekPixels\",\"resume\",\"stop\",\"reload\",\"release\"],"
           "\"ownedLibraryLoaded\":true,\"physicalOutputAccepted\":false}\n", video_tracks, audio_tracks,
           atomic_load(&observed.audio_peak), audio_frequency, video_codec, audio_codec);
cleanup:
    if (player) libvlc_media_player_release(player);
    if (media) libvlc_media_release(media);
    if (instance) libvlc_release(instance);
    return result;
}
