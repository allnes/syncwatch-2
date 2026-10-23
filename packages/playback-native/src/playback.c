/* SPDX-License-Identifier: Apache-2.0 */
#include "vlc_api.h"
#include "../include/syncwatch_playback.h"
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

struct sw_playback {
    sw_vlc_api api;
    sw_library *library;
    libvlc_instance_t *instance;
    libvlc_media_player_t *player;
    libvlc_event_manager_t *events;
    unsigned attached;
    uint64_t generation;
    int loaded;
    int failed;
    atomic_uint_fast64_t sequence;
};
static const libvlc_event_type_t event_types[] = {
    libvlc_MediaPlayerOpening, libvlc_MediaPlayerBuffering, libvlc_MediaPlayerPlaying,
    libvlc_MediaPlayerPaused, libvlc_MediaPlayerStopped, libvlc_MediaPlayerEndReached,
    libvlc_MediaPlayerEncounteredError, libvlc_MediaPlayerTimeChanged,
    libvlc_MediaPlayerLengthChanged, libvlc_MediaPlayerSeekableChanged,
    libvlc_MediaPlayerVout, libvlc_MediaPlayerESAdded, libvlc_MediaPlayerESDeleted,
    libvlc_MediaPlayerESSelected
};
static void changed(const libvlc_event_t *event, void *opaque) {
    (void)event;
    sw_playback *owner = opaque;
    /* No allocation, locks, UI, managed delegate or libVLC reentry here. */
    atomic_fetch_add_explicit(&owner->sequence, 1, memory_order_relaxed);
}
static int check(sw_playback *p, uint64_t generation) {
    if (!p) return SW_INVALID;
    if (generation != p->generation) return SW_STALE;
    return p->loaded ? SW_OK : SW_UNAVAILABLE;
}
int sw_playback_open(const char *path, const char *revision, int output, void *surface, sw_playback **result) {
    if (!result) return SW_INVALID;
    *result = NULL;
    if (!path || !revision || strlen(revision) != 40 || output < SW_OUTPUT_HEADLESS || output > SW_OUTPUT_HWND ||
        (output == SW_OUTPUT_HEADLESS ? surface != NULL : surface == NULL)) return SW_INVALID;
    const char *plugins = getenv("VLC_PLUGIN_PATH");
    if (plugins && *plugins) return SW_UNAVAILABLE;
#ifdef __APPLE__
    if (output == SW_OUTPUT_HWND) return SW_INVALID;
#elif defined(_WIN32)
    if (output == SW_OUTPUT_APPKIT) return SW_INVALID;
#else
    if (output != SW_OUTPUT_HEADLESS) return SW_UNAVAILABLE;
#endif
    sw_playback *p = calloc(1, sizeof(*p));
    if (!p) return SW_ENGINE;
    atomic_init(&p->sequence, 0);
    if (!sw_library_open(path, &p->api, output, &p->library)) { free(p); return SW_UNAVAILABLE; }
    if (strcmp(p->api.libvlc_get_version(), "3.0.24 Vetinari") || strcmp(p->api.libvlc_get_changeset(), revision)) {
        sw_playback_close(p); return SW_UNAVAILABLE;
    }
    /* Never silently select hardware paths whose controls are unqualified. */
    const char *options[] = {"--no-video-title-show", "--no-osd", "--no-snapshot-preview", "--no-plugins-cache",
        "--avcodec-hw=none", "--no-media-library", "--no-sub-autodetect-file",
        output == SW_OUTPUT_HEADLESS ? "--vout=dummy" :
            output == SW_OUTPUT_APPKIT ? "--vout=macosx" : "--vout=direct3d11",
        output == SW_OUTPUT_HEADLESS ? "--aout=dummy" :
            output == SW_OUTPUT_APPKIT ? "--aout=auhal" : "--aout=mmdevice"};
    p->instance = p->api.libvlc_new(sizeof(options) / sizeof(options[0]), options);
    if (!p->instance || !(p->player = p->api.libvlc_media_player_new(p->instance))) {
        sw_playback_close(p); return SW_ENGINE;
    }
    if (surface) p->api.set_surface(p->player, surface);
    p->events = p->api.libvlc_media_player_event_manager(p->player);
    for (unsigned i = 0; i < sizeof(event_types) / sizeof(event_types[0]); ++i) {
        if (p->api.libvlc_event_attach(p->events, event_types[i], changed, p)) {
            sw_playback_close(p); return SW_ENGINE;
        }
        p->attached++;
    }
    *result = p;
    return SW_OK;
}
int sw_playback_load(sw_playback *p, uint64_t generation, const char *path) {
    if (!p || !path || !path[0] || !generation || generation > UINT64_C(9007199254740991)) return SW_INVALID;
    if (generation <= p->generation) return SW_STALE;
    /* A local absolute file path only. No playlist, network URL or remote path. */
#ifdef _WIN32
    if (!((path[0] >= 'A' && path[0] <= 'Z') || (path[0] >= 'a' && path[0] <= 'z')) ||
        path[1] != ':' || (path[2] != '\\' && path[2] != '/')) return SW_INVALID;
#else
    if (path[0] != '/') return SW_INVALID;
#endif
    p->api.libvlc_media_player_stop(p->player);
    p->api.libvlc_media_player_set_media(p->player, NULL);
    p->generation = generation;
    p->loaded = 0;
    p->failed = 0;
    libvlc_media_t *media = p->api.libvlc_media_new_path(p->instance, path);
    if (!media) { p->failed = 1; return SW_ENGINE; }
    p->api.libvlc_media_add_option(media, ":start-paused");
    p->api.libvlc_media_player_set_media(p->player, media);
    p->api.libvlc_media_release(media);
    p->loaded = 1;
    if (p->api.libvlc_media_player_play(p->player)) { p->loaded = 0; p->failed = 1; return SW_ENGINE; }
    return SW_OK;
}
int sw_playback_observe(sw_playback *p, uint64_t generation, sw_observation *result) {
    if (!p || !result) return SW_INVALID;
    if (generation != p->generation) return SW_STALE;
    memset(result, 0, sizeof(*result));
    result->generation = p->generation;
    result->sequence = atomic_load_explicit(&p->sequence, memory_order_relaxed);
    result->duration_ms = -1; result->rate = 1; result->paused = 1;
    if (!p->loaded) { if (p->failed) result->status = SW_FAILED; return SW_OK; }
    libvlc_state_t state = p->api.libvlc_media_player_get_state(p->player);
    result->status = state == libvlc_Error ? SW_FAILED :
        (state == libvlc_Playing || state == libvlc_Paused || state == libvlc_Ended) ? SW_READY : SW_LOADING;
    result->buffering = state == libvlc_Buffering;
    result->ended = state == libvlc_Ended;
    if (result->status == SW_READY) {
        result->position_ms = p->api.libvlc_media_player_get_time(p->player);
        result->duration_ms = p->api.libvlc_media_player_get_length(p->player);
        if (result->duration_ms > INT64_C(604800000)) { result->status = SW_FAILED; result->position_ms = 0; result->duration_ms = -1; return SW_OK; }
        if (result->position_ms < 0) result->position_ms = 0;
        if (result->duration_ms >= 0 && result->position_ms > result->duration_ms) result->position_ms = result->duration_ms;
        result->paused = state != libvlc_Playing;
        result->seekable = p->api.libvlc_media_player_is_seekable(p->player);
        result->rate = p->api.libvlc_media_player_get_rate(p->player);
        if (!isfinite(result->rate) || result->rate < .25 || result->rate > 4) result->rate = 1;
    }
    result->video_outputs = (int32_t)p->api.libvlc_media_player_has_vout(p->player);
    unsigned width = 0, height = 0;
    if (!p->api.libvlc_video_get_size(p->player, 0, &width, &height) && width <= INT32_MAX && height <= INT32_MAX) {
        result->width = (int32_t)width; result->height = (int32_t)height;
    }
    result->volume = p->api.libvlc_audio_get_volume(p->player);
    result->muted = p->api.libvlc_audio_get_mute(p->player) == 1;
    return SW_OK;
}
int sw_playback_pause(sw_playback *p, uint64_t generation, int paused) {
    int code = check(p, generation); if (code) return code;
    if (paused != 0 && paused != 1) return SW_INVALID;
    p->api.libvlc_media_player_set_pause(p->player, paused); return SW_OK;
}
int sw_playback_seek(sw_playback *p, uint64_t generation, int64_t target) {
    int code = check(p, generation); if (code) return code;
    int64_t duration = p->api.libvlc_media_player_get_length(p->player);
    if (target < 0 || duration < 0 || target > duration || target > INT64_C(604800000)) return SW_INVALID;
    if (!p->api.libvlc_media_player_is_seekable(p->player)) return SW_UNAVAILABLE;
    p->api.libvlc_media_player_set_time(p->player, target); return SW_OK;
}
int sw_playback_rate(sw_playback *p, uint64_t generation, double rate) {
    int code = check(p, generation); if (code) return code;
    if (!isfinite(rate) || rate < .25 || rate > 4) return SW_INVALID;
    return p->api.libvlc_media_player_set_rate(p->player, (float)rate) ? SW_ENGINE : SW_OK;
}
int sw_playback_volume(sw_playback *p, uint64_t generation, double volume, int muted) {
    int code = check(p, generation); if (code) return code;
    if (!isfinite(volume) || volume < 0 || volume > 1 || (muted != 0 && muted != 1)) return SW_INVALID;
    if (p->api.libvlc_audio_set_volume(p->player, (int)lround(volume * 100))) return SW_ENGINE;
    p->api.libvlc_audio_set_mute(p->player, muted); return SW_OK;
}
int sw_playback_stop(sw_playback *p, uint64_t generation) {
    if (!p) return SW_INVALID;
    if (generation != p->generation) return SW_STALE;
    if (p->loaded) p->api.libvlc_media_player_stop(p->player);
    p->api.libvlc_media_player_set_media(p->player, NULL);
    p->loaded = 0; p->failed = 0; return SW_OK;
}
static libvlc_track_description_t *tracks(sw_playback *p, int subtitles) {
    return subtitles ? p->api.libvlc_video_get_spu_description(p->player) : p->api.libvlc_audio_get_track_description(p->player);
}
int sw_playback_tracks(sw_playback *p, uint64_t generation, int subtitles, int32_t *ids, size_t capacity, size_t *count) {
    int code = check(p, generation); if (code) return code;
    if (!count || (capacity && !ids) || capacity > 256 || (subtitles != 0 && subtitles != 1)) return SW_INVALID;
    libvlc_track_description_t *head = tracks(p, subtitles); size_t total = 0;
    for (libvlc_track_description_t *t = head; t; t = t->p_next) {
        if (total < capacity) ids[total] = t->i_id;
        total++;
    }
    p->api.libvlc_track_description_list_release(head); *count = total;
    return total <= capacity ? SW_OK : SW_UNAVAILABLE;
}
int sw_playback_track_name(sw_playback *p, uint64_t generation, int subtitles, int32_t id, char *utf8, size_t capacity) {
    int code = check(p, generation); if (code) return code;
    if (!utf8 || !capacity || capacity > 65536 || (subtitles != 0 && subtitles != 1)) return SW_INVALID;
    utf8[0] = 0; int result = SW_UNAVAILABLE;
    libvlc_track_description_t *head = tracks(p, subtitles);
    for (libvlc_track_description_t *t = head; t; t = t->p_next) {
        if (t->i_id == id && t->psz_name) {
            size_t size = strlen(t->psz_name);
            if (size < capacity) { memcpy(utf8, t->psz_name, size + 1); result = SW_OK; }
            break;
        }
    }
    p->api.libvlc_track_description_list_release(head); return result;
}
int sw_playback_select_track(sw_playback *p, uint64_t generation, int subtitles, int32_t id) {
    int code = check(p, generation); if (code) return code;
    if (subtitles != 0 && subtitles != 1) return SW_INVALID;
    libvlc_track_description_t *head = tracks(p, subtitles); int found = 0;
    for (libvlc_track_description_t *t = head; t; t = t->p_next) if (t->i_id == id) found = 1;
    p->api.libvlc_track_description_list_release(head);
    if (!found) return SW_INVALID;
    return (subtitles ? p->api.libvlc_video_set_spu(p->player, id) : p->api.libvlc_audio_set_track(p->player, id)) ? SW_ENGINE : SW_OK;
}
void sw_playback_close(sw_playback *p) {
    if (!p) return;
    /* detach synchronizes against in-flight callbacks before freeing opaque. */
    while (p->attached) p->api.libvlc_event_detach(p->events, event_types[--p->attached], changed, p);
    if (p->player) {
        p->api.libvlc_media_player_stop(p->player);
        p->api.libvlc_media_player_set_media(p->player, NULL);
        if (p->api.set_surface) p->api.set_surface(p->player, NULL);
        p->api.libvlc_media_player_release(p->player);
    }
    if (p->instance) p->api.libvlc_release(p->instance);
    sw_library_close(p->library);
    free(p);
}
