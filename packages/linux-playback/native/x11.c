/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE
#include "support.h"
#include <jawt.h>
#include <jawt_md.h>
#include <dlfcn.h>
#include <X11/Xlib.h>

#define X11_SURFACE_FUNCTIONS(X) \
    X(XOpenDisplay) X(XCloseDisplay) X(XDefaultRootWindow) X(XGetWindowAttributes) \
    X(XCreateSimpleWindow) X(XMapWindow) X(XUnmapWindow) X(XReparentWindow) \
    X(XMoveResizeWindow) X(XDestroyWindow) X(XQueryTree) X(XFree) X(XSync) X(XFlush)
typedef struct {
#define DECLARE(name) __typeof__(&name) name;
    X11_SURFACE_FUNCTIONS(DECLARE)
#undef DECLARE
} surface_api;
typedef struct {
    surface_api api;
    Display *display;
    Window window, parent, root;
    int parked;
} owned_surface;

static void destroy_surface(owned_surface *surface) {
    if (!surface) return;
    if (surface->display) {
        if (surface->window) {
            surface->api.XDestroyWindow(surface->display, surface->window);
            surface->api.XSync(surface->display, False);
        }
        surface->api.XCloseDisplay(surface->display);
    }
    free(surface);
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

JNIEXPORT jlongArray JNICALL Java_syncwatch_playback_X11Display_createOwned(JNIEnv *env, jclass type,
        jlong library, jobject canvas, jbyteArray jawt_library) {
    jlong parent = Java_syncwatch_playback_X11Display_drawable(env, type, library, canvas, jawt_library);
    if (!parent || (*env)->ExceptionCheck(env)) return NULL;
    owned_surface *surface = calloc(1, sizeof(*surface));
    if (!surface) { checked(env, SW_ENGINE); return NULL; }
#define BIND(name) { \
    void *address = dlsym((void *)(intptr_t)library, #name); \
    _Static_assert(sizeof(address) == sizeof(surface->api.name), "Xlib function pointer size"); \
    if (!address) goto failed; \
    memcpy(&surface->api.name, &address, sizeof(address)); }
    X11_SURFACE_FUNCTIONS(BIND)
#undef BIND
    surface->display = surface->api.XOpenDisplay(NULL);
    if (!surface->display) goto failed;
    surface->parent = (Window)parent;
    surface->root = surface->api.XDefaultRootWindow(surface->display);
    XWindowAttributes attributes;
    if (!surface->api.XGetWindowAttributes(surface->display, surface->parent, &attributes)
            || attributes.class != InputOutput || attributes.width < 1 || attributes.height < 1) goto failed;
    surface->window = surface->api.XCreateSimpleWindow(surface->display, surface->parent, 0, 0,
            (unsigned)attributes.width, (unsigned)attributes.height, 0, 0, 0);
    if (!surface->window || surface->window > UINT32_MAX) goto failed;
    surface->api.XMapWindow(surface->display, surface->window);
    surface->api.XSync(surface->display, False);
    jlong values[] = {(jlong)(intptr_t)surface, (jlong)surface->window};
    jlongArray result = (*env)->NewLongArray(env, 2);
    if (!result) { destroy_surface(surface); return NULL; }
    (*env)->SetLongArrayRegion(env, result, 0, 2, values);
    if ((*env)->ExceptionCheck(env)) { destroy_surface(surface); return NULL; }
    return result;
failed:
    destroy_surface(surface);
    checked(env, SW_UNAVAILABLE);
    return NULL;
}

JNIEXPORT void JNICALL Java_syncwatch_playback_X11Display_resizeOwned(JNIEnv *env, jclass type, jlong handle) {
    (void)type;
    owned_surface *surface = (owned_surface *)(intptr_t)handle;
    if (!surface) { checked(env, SW_INVALID); return; }
    if (surface->parked) return;
    XWindowAttributes attributes;
    if (!surface->api.XGetWindowAttributes(surface->display, surface->parent, &attributes)) {
        checked(env, SW_UNAVAILABLE); return;
    }
    if (attributes.width < 1 || attributes.height < 1) return;
    /* Server coordinates are physical pixels, including the Canvas's scale. */
    surface->api.XMoveResizeWindow(surface->display, surface->window, 0, 0,
            (unsigned)attributes.width, (unsigned)attributes.height);
    surface->api.XFlush(surface->display);
}

JNIEXPORT void JNICALL Java_syncwatch_playback_X11Display_parkOwned(JNIEnv *env, jclass type, jlong handle) {
    (void)type;
    owned_surface *surface = (owned_surface *)(intptr_t)handle;
    if (!surface) { checked(env, SW_INVALID); return; }
    if (surface->parked) return;
    surface->api.XUnmapWindow(surface->display, surface->window);
    surface->api.XReparentWindow(surface->display, surface->window, surface->root, 0, 0);
    /* Complete this connection's reparent before AWT may destroy the parent
     * through its separate display connection. No engine call runs here. */
    surface->api.XSync(surface->display, False);
    surface->parked = 1;
}

JNIEXPORT jboolean JNICALL Java_syncwatch_playback_X11Display_isParkedOwned(JNIEnv *env, jclass type, jlong handle) {
    (void)env; (void)type;
    owned_surface *surface = (owned_surface *)(intptr_t)handle;
    if (!surface || !surface->parked) return JNI_FALSE;
    Window root, parent, *children = NULL;
    unsigned count;
    int found = surface->api.XQueryTree(surface->display, surface->window, &root, &parent, &children, &count);
    if (children) surface->api.XFree(children);
    XWindowAttributes attributes;
    return found && root == surface->root && parent == surface->root
        && surface->api.XGetWindowAttributes(surface->display, surface->window, &attributes)
        && attributes.map_state == IsUnmapped ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT void JNICALL Java_syncwatch_playback_X11Display_destroyOwned(JNIEnv *env, jclass type, jlong handle) {
    (void)env; (void)type;
    destroy_surface((owned_surface *)(intptr_t)handle);
}
