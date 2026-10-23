/* SPDX-License-Identifier: Apache-2.0 */
#include "probe_common.h"

int main(int argc, char **argv) {
    const char *base_options[] = {"--ignore-config", "--no-plugins-cache", "--no-media-library",
        "--no-video-title-show", "--no-osd", "--no-sub-autodetect-file",
        "--avcodec-hw=none", "--vout=vmem", "--aout=amem", "--quiet"};
    const char *options[sizeof(base_options) / sizeof(base_options[0]) + 3];
    unsigned option_count = 0;
    struct observations observed = {0};
    libvlc_instance_t *instance = NULL;
    libvlc_media_t *media = NULL;
    libvlc_media_player_t *player = NULL;
    int result = 0;
    unsigned video_tracks = 0, audio_tracks = 0, paused_frames, paused_pixel, audio_frequency = 0;
    uint32_t video_codec = 0, audio_codec = 0;
    unsigned hardware_before_reload;
    unsigned expected_width, expected_height;
    int hardware_mode;
    char *end;
    libvlc_time_t paused_time;
    libvlc_media_track_t **tracks = NULL;
    uint64_t deadline;
    if (argc != 5 && argc != 6) { fprintf(stderr, "usage: vlc-probe owned-media-path expected-library-path input-width input-height [videotoolbox]\n"); return 2; }
    hardware_mode = argc == 6 && strcmp(argv[5], "videotoolbox") == 0;
    REQUIRE(argc == 5 || hardware_mode, "unknown diagnostic decoder mode");
    expected_width = (unsigned)strtoul(argv[3], &end, 10);
    REQUIRE(*end == '\0' && expected_width > 0 && expected_width <= 8192, "invalid fixture width");
    expected_height = (unsigned)strtoul(argv[4], &end, 10);
    REQUIRE(*end == '\0' && expected_height > 0 && expected_height <= 8192, "invalid fixture height");
    REQUIRE(owned_library(argv[2]), "loaded library is not the owned relocated artifact");
    REQUIRE(load_owned_dependencies(), "cannot load the owned native dependency closure");
    for (unsigned i = 0; i < sizeof(base_options) / sizeof(base_options[0]); ++i) options[option_count++] = base_options[i];
    options[option_count++] = hardware_mode ? "--codec=videotoolbox" : "--codec=avcodec,rawvideo,araw";
    if (hardware_mode) {
        // Audio is exercised by the software matrix. Restricting this diagnostic
        // to one video decoder makes a silent software fallback impossible.
        options[option_count++] = "--videotoolbox-hw-decoder-only";
        options[option_count++] = "--no-audio";
    }
    instance = libvlc_new((int)option_count, options);
    REQUIRE(instance, "cannot create owned native instance");
    libvlc_log_set(instance, observe_log, &observed);
    REQUIRE(strncmp(libvlc_get_version(), "3.0.24 ", 7) == 0, "unexpected native version");
    REQUIRE(strcmp(libvlc_get_changeset(), SW_VLC_REVISION) == 0, "unexpected native source revision");
    media = libvlc_media_new_path(instance, argv[1]);
    REQUIRE(media, "cannot create file media");
    REQUIRE(libvlc_media_parse_with_options(media, libvlc_media_parse_local, 10000) == 0,
            "metadata parse rejected");
    deadline = milliseconds() + 12000;
    while (libvlc_media_get_parsed_status(media) != libvlc_media_parsed_status_done && milliseconds() < deadline) delay();
    REQUIRE(libvlc_media_get_parsed_status(media) == libvlc_media_parsed_status_done, "metadata parse timed out");
    unsigned count = libvlc_media_tracks_get(media, &tracks);
    for (unsigned i = 0; i < count; ++i) {
        if (tracks[i]->i_type == libvlc_track_video && tracks[i]->video->i_width == expected_width && tracks[i]->video->i_height == expected_height) {
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
    // Unlock belongs to Prepare(), ahead of the presentation clock. Observe
    // Display() so pause and seeking are checked against presented pixels.
    libvlc_video_set_callbacks(player, lock_video, NULL, display_video, &observed);
    libvlc_video_set_format(player, "RV32", WIDTH, HEIGHT, PITCH);
    libvlc_audio_set_callbacks(player, play_audio, NULL, NULL, NULL, NULL, &observed);
    libvlc_audio_set_format(player, "S16N", 44100, 2);
    REQUIRE(libvlc_media_player_play(player) == 0 && wait_state(player, libvlc_Playing), "play not observed");
    REQUIRE(wait_frames(&observed, 5, 1), "no decoded frames");
    if (!hardware_mode) {
        REQUIRE(wait_audio(&observed), "no decoded PCM audio");
        audio_frequency = atomic_load(&observed.positive_crossings) * 44100 / atomic_load(&observed.audio_samples);
        REQUIRE(audio_frequency >= 430 && audio_frequency <= 450, "PCM rate conversion did not preserve the known tone");
    }
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
    // A forward-only observation could also occur by letting the movie play.
    // Its encoded luminance increases monotonically; a backward jump proves
    // actual decoder seeking independently of the requested media clock.
    libvlc_media_player_set_pause(player, 1);
    REQUIRE(wait_state(player, libvlc_Paused), "pause before backward seek not observed");
    paused_frames = atomic_load(&observed.frames);
    atomic_store(&observed.minimum_luminance, 255);
    libvlc_media_player_set_time(player, 250);
    libvlc_media_player_set_pause(player, 0);
    REQUIRE(wait_low_frames(&observed, paused_frames + 3), "backward seek not observed in decoded pixels");
    libvlc_media_player_stop(player);
    hardware_before_reload = atomic_load(&observed.hardware_sessions);
    REQUIRE(!hardware_mode || (hardware_before_reload >= 1 &&
            atomic_load(&observed.hardware_errors) == 0), "required native hardware decoder was not observed");
    REQUIRE(wait_state(player, libvlc_Stopped), "stop not observed");
    atomic_store(&observed.frames, 0); atomic_store(&observed.luminance, 0);
    REQUIRE(libvlc_media_player_play(player) == 0 && wait_frames(&observed, 3, 1), "reload did not decode frames");
    REQUIRE(atomic_load(&observed.luminance) < 100, "reload did not restart actual media");
    libvlc_media_player_stop(player);
    REQUIRE(!hardware_mode || (atomic_load(&observed.hardware_sessions) > hardware_before_reload &&
            atomic_load(&observed.hardware_errors) == 0), "native hardware decoder was not observed after reload");
    printf("{\"version\":\"3.0.24\",\"videoTracks\":%u,\"audioTracks\":%u,"
           "\"inputWidth\":%u,\"inputHeight\":%u,\"audioPeak\":%u,\"resampledToneHz\":%u,\"videoCodec\":\"%08x\",\"audioCodec\":\"%08x\","
           "\"cases\":[\"metadata\",\"decodeVideo\",%s"
           "\"play\",\"pause\",\"seekPixels\",\"resume\",\"stop\",\"reload\",\"release\"],"
           "\"hardwareDecoderObserved\":%s,\"ownedLibraryLoaded\":true,\"physicalOutputAccepted\":false}\n", video_tracks, audio_tracks,
           expected_width, expected_height, atomic_load(&observed.audio_peak), audio_frequency, video_codec, audio_codec,
           hardware_mode ? "" : "\"decodeAudio\",",
           hardware_mode ? "true" : "false");
cleanup:
    if (player) libvlc_media_player_release(player);
    if (media) libvlc_media_release(media);
    if (instance) libvlc_release(instance);
    release_owned_dependencies();
    return result;
}
