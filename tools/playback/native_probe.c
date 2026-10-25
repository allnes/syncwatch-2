/* SPDX-License-Identifier: Apache-2.0 */
#include "../../packages/playback-native/include/syncwatch_playback.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#ifdef _WIN32
#include <windows.h>
static void wait_ms(unsigned ms) { Sleep(ms); }
#else
#include <time.h>
static void wait_ms(unsigned ms) {
    struct timespec value = {ms / 1000, (long)(ms % 1000) * 1000000};
    nanosleep(&value, NULL);
}
#endif
static void require(int condition, const char *label) {
    if (!condition) { fprintf(stderr, "Playback acceptance: %s\n", label); exit(1); }
}
static sw_observation observation(sw_playback *p, uint64_t generation) {
    sw_observation value;
    require(sw_playback_observe(p, generation, &value) == SW_OK, "observation");
    require(value.generation == generation && isfinite(value.rate), "observation identity");
    require(value.position_ms >= 0 && (value.duration_ms < 0 || value.position_ms <= value.duration_ms), "observed clock bounds");
    return value;
}
static sw_observation await_state_at(int line, sw_playback *p, uint64_t generation, int paused, int64_t minimum, int64_t maximum) {
    sw_observation value = {0};
    for (int i = 0; i < 600; i++) {
        value = observation(p, generation);
        if (value.status == SW_READY && !value.ended && value.paused == paused && value.position_ms >= minimum && value.position_ms <= maximum) return value;
        if (value.status == SW_FAILED || value.ended) break;
        wait_ms(20);
    }
    fprintf(stderr, "line=%d expected_paused=%d range=[%lld,%lld] state=%d paused=%d position=%lld duration=%lld outputs=%d ended=%d\n",
            line, paused, (long long)minimum, (long long)maximum, value.status, value.paused,
            (long long)value.position_ms, (long long)value.duration_ms, value.video_outputs, value.ended);
    require(0, "bounded native state transition"); return value;
}
#define await_state(...) await_state_at(__LINE__, __VA_ARGS__)
int main(int argc, char **argv) {
    require(argc == 4, "arguments");
    sw_playback *player = NULL;
    require(sizeof(sw_observation) == 80, "fixed ABI layout");
    require(sw_playback_open(argv[1], argv[2], SW_OUTPUT_X11, (void *)(uintptr_t)1, &player) == SW_INVALID && !player,
            "XID cannot enter the pointer surface ABI");
    require(sw_playback_open_x11(argv[1], argv[2], 0, &player) == SW_INVALID && !player, "zero XID rejection");
#if defined(__APPLE__) || defined(_WIN32)
    require(sw_playback_open_x11(argv[1], argv[2], 1, &player) == SW_INVALID && !player, "foreign platform output rejection");
#endif
    require(sw_playback_open(argv[1], "0000000000000000000000000000000000000000", 0, NULL, &player) == SW_UNAVAILABLE && !player, "foreign revision rejection");
    require(sw_playback_open(argv[1], argv[2], 0, NULL, &player) == SW_OK, "owned runtime");
    sw_observation value = observation(player, 0);
    require(value.status == SW_UNLOADED && value.paused && value.position_ms == 0 && value.duration_ms == -1, "initial state");
    require(sw_playback_load(player, 1, "https://invalid.example/movie") == SW_INVALID, "network path rejection");
    require(sw_playback_load(player, 1, argv[3]) == SW_OK, "paused local load");
    value = await_state(player, 1, 1, 0, 300);
    require(value.duration_ms >= 3800 && value.duration_ms <= 4200 && value.seekable, "real duration and seekability");
    uint64_t start_sequence = value.sequence;
    require(sw_playback_load(player, 1, argv[3]) == SW_STALE, "duplicate generation rejection");
    require(sw_playback_rate(player, 1, NAN) == SW_INVALID && sw_playback_volume(player, 1, INFINITY, 0) == SW_INVALID, "nonfinite rejection");
    require(sw_playback_seek(player, 1, value.duration_ms + 1) == SW_INVALID, "seek bounds");
    int32_t ids[256]; size_t count;
    require(sw_playback_tracks(player, 1, 0, ids, 256, &count) == SW_OK && count > 0, "actual audio tracks");
    char name[65536];
    require(sw_playback_track_name(player, 1, 0, ids[count - 1], name, sizeof(name)) == SW_OK && name[0], "actual track name");
    require(sw_playback_select_track(player, 1, 0, INT32_MAX) == SW_INVALID, "foreign track rejection");
    require(sw_playback_pause(player, 1, 0) == SW_OK, "play submission");
    value = await_state(player, 1, 0, 400, 1500);
    require(sw_playback_pause(player, 1, 1) == SW_OK, "pause submission");
    value = await_state(player, 1, 1, 0, 2000);
    int64_t before = value.position_ms; wait_ms(300); value = observation(player, 1);
    require(value.paused && llabs(value.position_ms - before) <= 60, "actual paused clock");
    require(sw_playback_seek(player, 1, 2500) == SW_OK, "forward seek submission");
    await_state(player, 1, 1, 2300, 2700);
    require(sw_playback_pause(player, 1, 0) == SW_OK, "forward resume");
    /* Resume is a Playing observation in the already verified seek range.
     * Requiring another 300 ms timestamp publication near this short fixture's
     * EOF can miss Playing before EndReached. Clock advance was tested above. */
    await_state(player, 1, 0, 2300, 4000);
    require(sw_playback_pause(player, 1, 1) == SW_OK, "second pause");
    await_state(player, 1, 1, 2300, 4000);
    require(sw_playback_seek(player, 1, 250) == SW_OK, "backward seek submission");
    await_state(player, 1, 1, 0, 650);
    require(sw_playback_rate(player, 1, 1.25) == SW_OK, "local correction rate");
    require(sw_playback_rate(player, 1, 1) == SW_OK, "restore correction rate");
    require(sw_playback_stop(player, 1) == SW_OK && sw_playback_stop(player, 1) == SW_OK, "idempotent stop");
    value = observation(player, 1); require(value.status == SW_UNLOADED && value.position_ms == 0, "observed release");
    require(sw_playback_pause(player, 1, 0) == SW_UNAVAILABLE, "no stopped resurrection");
    require(sw_playback_load(player, 2, argv[3]) == SW_OK, "new generation reload");
    await_state(player, 2, 1, 0, 300);
    require(sw_playback_seek(player, 1, 0) == SW_STALE && sw_playback_observe(player, 1, &value) == SW_STALE, "stale native commands and observations");
    value = observation(player, 2); require(value.sequence > start_sequence, "native event callbacks");
    sw_playback_close(player);
    for (int i = 0; i < 8; i++) {
        player = NULL;
        require(sw_playback_open(argv[1], argv[2], 0, NULL, &player) == SW_OK, "repeated instance ownership");
        require(sw_playback_load(player, 1, argv[3]) == SW_OK, "repeated local load");
        await_state(player, 1, 1, 0, 300);
        sw_playback_close(player);
    }
    sw_runtime *runtime = NULL;
    sw_playback *second = NULL;
    require(sw_runtime_open(argv[1], argv[2], SW_OUTPUT_HEADLESS, &runtime) == SW_OK, "application runtime");
    require(sw_playback_open_runtime(runtime, (void *)(uintptr_t)1, 0, &player) == SW_INVALID && !player, "runtime surface validation");
    for (int i = 0; i < 3; i++) {
        require(sw_playback_open_runtime(runtime, NULL, 0, &player) == SW_OK, "shared runtime player");
        require(sw_playback_load(player, 1, argv[3]) == SW_OK, "shared runtime load");
        await_state(player, 1, 1, 0, 300);
        sw_playback_close(player);
    }
    require(sw_playback_open_runtime(runtime, NULL, 0, &player) == SW_OK, "first retained player");
    require(sw_playback_open_runtime(runtime, NULL, 0, &second) == SW_OK, "second retained player");
    sw_runtime_close(runtime);
    require(sw_playback_load(player, 1, argv[3]) == SW_OK, "player outlives runtime handle");
    require(sw_playback_load(second, 1, argv[3]) == SW_OK, "second player outlives runtime handle");
    await_state(player, 1, 1, 0, 300); await_state(second, 1, 1, 0, 300);
    sw_playback_close(player);
    require(sw_playback_seek(second, 1, 1300) == SW_OK, "peer player survives release");
    await_state(second, 1, 1, 1100, 1500);
    sw_playback_close(second);
    puts("{\"abiBytes\":80,\"ownedRuntime\":true,\"pausedLoad\":true,\"actualClock\":true,\"nativeEvents\":true,\"tracks\":true,\"generationRejection\":true,\"networkPathRejected\":true,\"repeatedRelease\":true,\"sharedRuntime\":true,\"physicalOutputAccepted\":false}");
    return 0;
}
