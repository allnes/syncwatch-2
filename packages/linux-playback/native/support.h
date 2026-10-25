/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SW_JNI_SUPPORT_H
#define SW_JNI_SUPPORT_H
#include <jni.h>
#include <stdlib.h>
#include <string.h>
#include "../../playback-native/include/syncwatch_playback.h"
static inline int checked(JNIEnv *env, int code) {
    if (!code) return 1;
    jclass type = (*env)->FindClass(env, "java/lang/IllegalStateException");
    if (type) (*env)->ThrowNew(env, type, code == SW_STALE ? "stale" : code == SW_INVALID ? "invalid" : code == SW_UNAVAILABLE ? "unavailable" : "engine");
    return 0;
}
/* JNI's modified UTF-8 is unsuitable for filesystem paths containing emoji.
 * The Java boundary supplies ordinary UTF-8 bytes with no embedded NUL. */
static inline char *text(JNIEnv *env, jbyteArray bytes) {
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
#endif
