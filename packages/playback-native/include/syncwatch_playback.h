/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SYNCWATCH_PLAYBACK_H
#define SYNCWATCH_PLAYBACK_H
#include <stdint.h>
#include <stddef.h>
#ifdef _WIN32
#define SW_PLAYBACK_API __declspec(dllexport)
#else
#define SW_PLAYBACK_API __attribute__((visibility("default")))
#endif
#ifdef __cplusplus
extern "C" {
#endif

typedef struct sw_playback sw_playback;
typedef struct sw_runtime sw_runtime;
enum sw_result { SW_OK, SW_INVALID, SW_UNAVAILABLE, SW_STALE, SW_ENGINE };
enum sw_output { SW_OUTPUT_HEADLESS, SW_OUTPUT_APPKIT, SW_OUTPUT_HWND, SW_OUTPUT_X11 };
enum sw_status { SW_UNLOADED, SW_LOADING, SW_READY, SW_FAILED };
/* Fixed-width values only: identical C, Swift, .NET and JNI layouts. */
typedef struct sw_observation {
    uint64_t generation;
    uint64_t sequence;
    int64_t position_ms;
    int64_t duration_ms; /* -1 until the engine knows the duration. */
    double rate;
    int32_t status;
    int32_t paused;
    int32_t seekable;
    int32_t buffering;
    int32_t ended;
    int32_t video_outputs;
    int32_t width;
    int32_t height;
    int32_t volume;
    int32_t muted;
} sw_observation;

/* An application runtime owns the verified engine/plugin bank independently of
 * individual media players. Serialize open/close on its owner; each player
 * retains it until native close. Releasing a media owner never unloads a bank
 * that is still in use by the application or another player. */
SW_PLAYBACK_API int sw_runtime_open(const char *library, const char *revision, int output, sw_runtime **result);
SW_PLAYBACK_API void sw_runtime_close(sw_runtime *);
SW_PLAYBACK_API int sw_playback_open_runtime(sw_runtime *, void *surface, uint32_t drawable, sw_playback **result);

/* One serialized worker owns every call, including close. Callbacks never call
 * a client. The caller must retain its NSView/HWND until close returns. The
 * package must have passed the host's receipt/integrity check before open. */
SW_PLAYBACK_API int sw_playback_open(const char *library, const char *revision,
    int output, void *surface, sw_playback **result);
/* XIDs have their original uint32 ABI, never a void-pointer representation.
 * The host must initialize Xlib threading before any display is opened and
 * retain this Input/Output drawable until serialized close returns. The
 * pointer-based open deliberately rejects SW_OUTPUT_X11. */
SW_PLAYBACK_API int sw_playback_open_x11(const char *library, const char *revision,
    uint32_t drawable, sw_playback **result);
/* Loading starts paused. A request is never reported as an observation. */
SW_PLAYBACK_API int sw_playback_load(sw_playback *, uint64_t generation, const char *local_path);
SW_PLAYBACK_API int sw_playback_observe(sw_playback *, uint64_t generation, sw_observation *);
SW_PLAYBACK_API int sw_playback_pause(sw_playback *, uint64_t generation, int paused);
SW_PLAYBACK_API int sw_playback_seek(sw_playback *, uint64_t generation, int64_t position_ms);
SW_PLAYBACK_API int sw_playback_rate(sw_playback *, uint64_t generation, double rate);
SW_PLAYBACK_API int sw_playback_volume(sw_playback *, uint64_t generation, double volume, int muted);
SW_PLAYBACK_API int sw_playback_stop(sw_playback *, uint64_t generation);
SW_PLAYBACK_API int sw_playback_tracks(sw_playback *, uint64_t generation, int subtitles,
    int32_t *ids, size_t capacity, size_t *count);
SW_PLAYBACK_API int sw_playback_track_name(sw_playback *, uint64_t generation, int subtitles,
    int32_t id, char *utf8, size_t capacity);
SW_PLAYBACK_API int sw_playback_select_track(sw_playback *, uint64_t generation, int subtitles, int32_t id);
SW_PLAYBACK_API void sw_playback_close(sw_playback *);
#ifdef __cplusplus
}
#endif
#endif
