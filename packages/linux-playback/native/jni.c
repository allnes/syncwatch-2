/* SPDX-License-Identifier: Apache-2.0 */
#include "support.h"
#define JNI_METHOD(name) Java_syncwatch_playback_NativePlayback_##name
JNIEXPORT jlong JNICALL JNI_METHOD(open)(JNIEnv *env, jclass type, jbyteArray library, jbyteArray revision) {
    (void)type;
    char *path = text(env, library); if (!path) return 0;
    char *pin = text(env, revision); if (!pin) { free(path); return 0; }
    sw_playback *player = NULL;
    int code = sw_playback_open(path, pin, SW_OUTPUT_HEADLESS, NULL, &player);
    free(path); free(pin);
    if (!checked(env, code)) return 0;
    return (jlong)(intptr_t)player;
}
JNIEXPORT jlong JNICALL JNI_METHOD(openX11)(JNIEnv *env, jclass type, jbyteArray library, jbyteArray revision, jlong drawable) {
    (void)type;
    if (drawable <= 0 || (uint64_t)drawable > UINT32_MAX) { checked(env, SW_INVALID); return 0; }
    char *path = text(env, library); if (!path) return 0;
    char *pin = text(env, revision); if (!pin) { free(path); return 0; }
    sw_playback *player = NULL;
    int code = sw_playback_open_x11(path, pin, (uint32_t)drawable, &player);
    free(path); free(pin);
    if (!checked(env, code)) return 0;
    return (jlong)(intptr_t)player;
}

JNIEXPORT jint JNICALL JNI_METHOD(load)(JNIEnv *env, jclass type, jlong player, jlong generation, jbyteArray file) {
    (void)type; char *path = text(env, file); if (!path) return SW_INVALID;
    int result = sw_playback_load((sw_playback *)(intptr_t)player, (uint64_t)generation, path); free(path); return result;
}
JNIEXPORT jlongArray JNICALL JNI_METHOD(observe)(JNIEnv *env, jclass type, jlong player, jlong generation) {
    (void)type; sw_observation value;
    if (!checked(env, sw_playback_observe((sw_playback *)(intptr_t)player, (uint64_t)generation, &value))) return NULL;
    jlong rate; _Static_assert(sizeof(rate) == sizeof(value.rate), "IEEE binary64"); memcpy(&rate, &value.rate, sizeof(rate));
    jlong values[] = {(jlong)value.generation, (jlong)value.sequence, value.position_ms, value.duration_ms, rate,
        value.status, value.paused, value.seekable, value.buffering, value.ended, value.video_outputs,
        value.width, value.height, value.volume, value.muted};
    jlongArray result = (*env)->NewLongArray(env, 15);
    if (result) (*env)->SetLongArrayRegion(env, result, 0, 15, values);
    return result;
}
JNIEXPORT jlongArray JNICALL JNI_METHOD(contentVersion)(JNIEnv *env, jclass type, jlong player, jlong generation) {
    (void)type; sw_input_version version;
    if (!checked(env, sw_playback_input_version((sw_playback *)(intptr_t)player, (uint64_t)generation, &version))) return NULL;
    jlong values[8];
    _Static_assert(sizeof(values) == sizeof(version), "Local version JNI layout");
    memcpy(values, version.words, sizeof(values));
    jlongArray result = (*env)->NewLongArray(env, 8);
    if (result) (*env)->SetLongArrayRegion(env, result, 0, 8, values);
    return result;
}
JNIEXPORT jbyteArray JNICALL JNI_METHOD(readContent)(JNIEnv *env, jclass type, jlong player, jlong generation,
    jlong offset, jint capacity) {
    (void)type;
    if (offset < 0 || capacity < 1 || capacity > 262144) { checked(env, SW_INVALID); return NULL; }
    unsigned char *buffer = malloc((size_t)capacity);
    if (!buffer) { checked(env, SW_ENGINE); return NULL; }
    size_t count = 0;
    int code = sw_playback_read_at((sw_playback *)(intptr_t)player, (uint64_t)generation, (uint64_t)offset,
        buffer, (size_t)capacity, &count);
    jbyteArray result = NULL;
    if (checked(env, code) && count <= (size_t)capacity) {
        result = (*env)->NewByteArray(env, (jsize)count);
        if (result) (*env)->SetByteArrayRegion(env, result, 0, (jsize)count, (const jbyte *)buffer);
    }
    if (count > (size_t)capacity) checked(env, SW_ENGINE);
    free(buffer);
    return result;
}
JNIEXPORT void JNICALL JNI_METHOD(pause)(JNIEnv *env, jclass type, jlong p, jlong g, jboolean v) {
    (void)type; checked(env, sw_playback_pause((sw_playback *)(intptr_t)p, (uint64_t)g, v == JNI_TRUE));
}
JNIEXPORT void JNICALL JNI_METHOD(seek)(JNIEnv *env, jclass type, jlong p, jlong g, jlong v) {
    (void)type; checked(env, sw_playback_seek((sw_playback *)(intptr_t)p, (uint64_t)g, v));
}
JNIEXPORT void JNICALL JNI_METHOD(rate)(JNIEnv *env, jclass type, jlong p, jlong g, jdouble v) {
    (void)type; checked(env, sw_playback_rate((sw_playback *)(intptr_t)p, (uint64_t)g, v));
}
JNIEXPORT void JNICALL JNI_METHOD(volume)(JNIEnv *env, jclass type, jlong p, jlong g, jdouble v, jboolean mute) {
    (void)type; checked(env, sw_playback_volume((sw_playback *)(intptr_t)p, (uint64_t)g, v, mute == JNI_TRUE));
}
JNIEXPORT void JNICALL JNI_METHOD(stop)(JNIEnv *env, jclass type, jlong p, jlong g) {
    (void)type; checked(env, sw_playback_stop((sw_playback *)(intptr_t)p, (uint64_t)g));
}
JNIEXPORT void JNICALL JNI_METHOD(close)(JNIEnv *env, jclass type, jlong p) {
    (void)env; (void)type; sw_playback_close((sw_playback *)(intptr_t)p);
}
JNIEXPORT jintArray JNICALL JNI_METHOD(trackIds)(JNIEnv *env, jclass type, jlong p, jlong g, jboolean subtitles) {
    (void)type; int32_t ids[256]; size_t count = 0;
    if (!checked(env, sw_playback_tracks((sw_playback *)(intptr_t)p, (uint64_t)g, subtitles == JNI_TRUE, ids, 256, &count))) return NULL;
    jintArray result = (*env)->NewIntArray(env, (jsize)count);
    if (result) (*env)->SetIntArrayRegion(env, result, 0, (jsize)count, (const jint *)ids);
    return result;
}
JNIEXPORT jbyteArray JNICALL JNI_METHOD(trackName)(JNIEnv *env, jclass type, jlong p, jlong g, jboolean subtitles, jint id) {
    (void)type; char name[65536];
    if (!checked(env, sw_playback_track_name((sw_playback *)(intptr_t)p, (uint64_t)g, subtitles == JNI_TRUE, id, name, sizeof(name)))) return NULL;
    jsize size = (jsize)strlen(name);
    jbyteArray result = (*env)->NewByteArray(env, size);
    if (result) (*env)->SetByteArrayRegion(env, result, 0, size, (const jbyte *)name);
    return result;
}
JNIEXPORT void JNICALL JNI_METHOD(selectTrack)(JNIEnv *env, jclass type, jlong p, jlong g, jboolean subtitles, jint id) {
    (void)type; checked(env, sw_playback_select_track((sw_playback *)(intptr_t)p, (uint64_t)g, subtitles == JNI_TRUE, id));
}
