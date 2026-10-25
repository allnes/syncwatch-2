/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE
#include <jni.h>
#include <jawt.h>
#include <jawt_md.h>
#include <dlfcn.h>
#include <X11/Xlib.h>
#include <stdlib.h>
#include <string.h>
#include "../../playback-native/include/syncwatch_playback.h"
#define JNI_METHOD(name) Java_syncwatch_playback_NativePlayback_##name
static int checked(JNIEnv *env, int code) {
    if (!code) return 1;
    jclass type = (*env)->FindClass(env, "java/lang/IllegalStateException");
    if (type) (*env)->ThrowNew(env, type, code == SW_STALE ? "stale" : code == SW_INVALID ? "invalid" : code == SW_UNAVAILABLE ? "unavailable" : "engine");
    return 0;
}
/* JNI's modified UTF-8 is unsuitable for filesystem paths containing emoji.
 * The Java boundary supplies ordinary UTF-8 bytes with no embedded NUL. */
static char *text(JNIEnv *env, jbyteArray bytes) {
    if (!bytes) { checked(env, SW_INVALID); return NULL; }
    jsize size = (*env)->GetArrayLength(env, bytes);
    if (size <= 0 || size > 65535) { checked(env, SW_INVALID); return NULL; }
    char *value = malloc((size_t)size + 1);
    if (!value) { checked(env, SW_ENGINE); return NULL; }
    (*env)->GetByteArrayRegion(env, bytes, 0, size, (jbyte *)value);
    if ((*env)->ExceptionCheck(env)) { free(value); return NULL; }
    if (memchr(value, 0, (size_t)size)) { free(value); checked(env, SW_INVALID); return NULL; }
    value[size] = 0; return value;
}
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

static void *owned_symbol(const char *path, const char *name, void **library) {
    if (path[0] != '/') return NULL;
    *library = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!*library) return NULL;
    void *address = dlsym(*library, name);
    Dl_info info;
    char *expected = realpath(path, NULL), *actual = NULL;
    if (address && dladdr(address, &info)) actual = realpath(info.dli_fname, NULL);
    int owned = expected && actual && !strcmp(expected, actual);
    free(expected); free(actual);
    if (!owned) { dlclose(*library); *library = NULL; return NULL; }
    return address;
}

JNIEXPORT jlong JNICALL Java_syncwatch_playback_X11Display_initialize(JNIEnv *env, jclass type, jbyteArray library) {
    (void)type;
    char *path = text(env, library); if (!path) return 0;
    void *handle = NULL, *address = owned_symbol(path, "XInitThreads", &handle);
    free(path);
    int (*initialize)(void);
    _Static_assert(sizeof(initialize) == sizeof(address), "Xlib function pointer size");
    memcpy(&initialize, &address, sizeof(address));
    if (!initialize || !initialize()) {
        if (handle) dlclose(handle);
        checked(env, SW_UNAVAILABLE); return 0;
    }
    /* Intentional process-lifetime reference; AWT may continue to use Xlib
     * after individual players/surfaces close. No late toolkit initialization. */
    return (jlong)(intptr_t)handle;
}

JNIEXPORT jlong JNICALL Java_syncwatch_playback_X11Display_drawable(JNIEnv *env, jclass type,
        jlong library, jobject canvas, jbyteArray jawtLibrary) {
    (void)type;
    if (!library || !canvas) { checked(env, SW_INVALID); return 0; }
    char *path = text(env, jawtLibrary); if (!path) return 0;
    void *handle = NULL, *address = owned_symbol(path, "JAWT_GetAWT", &handle);
    free(path);
    jboolean (JNICALL *get_awt)(JNIEnv *, JAWT *);
    _Static_assert(sizeof(get_awt) == sizeof(address), "JAWT function pointer size");
    memcpy(&get_awt, &address, sizeof(address));
    JAWT awt = { .version = JAWT_VERSION_1_7 };
    JAWT_DrawingSurface *surface = NULL;
    JAWT_DrawingSurfaceInfo *info = NULL;
    jlong drawable = 0;
    int locked = 0;
    if (!get_awt || !get_awt(env, &awt) || !(surface = awt.GetDrawingSurface(env, canvas))) goto done;
    if (surface->Lock(surface) & JAWT_LOCK_ERROR) goto done;
    locked = 1;
    info = surface->GetDrawingSurfaceInfo(surface);
    if (!info || !info->platformInfo) goto done;
    JAWT_X11DrawingSurfaceInfo *x11 = info->platformInfo;
    if (!x11->drawable || x11->drawable > UINT32_MAX || !x11->display) goto done;
    int (*attributes)(Display *, Window, XWindowAttributes *);
    address = dlsym((void *)(intptr_t)library, "XGetWindowAttributes");
    _Static_assert(sizeof(attributes) == sizeof(address), "Xlib attribute function size");
    memcpy(&attributes, &address, sizeof(address));
    XWindowAttributes value;
    if (attributes && attributes(x11->display, x11->drawable, &value) && value.class == InputOutput)
        drawable = (jlong)x11->drawable;
done:
    if (info) surface->FreeDrawingSurfaceInfo(info);
    if (locked) surface->Unlock(surface);
    if (surface) awt.FreeDrawingSurface(surface);
    if (handle) dlclose(handle);
    if (!drawable && !(*env)->ExceptionCheck(env)) checked(env, SW_UNAVAILABLE);
    return drawable;
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
