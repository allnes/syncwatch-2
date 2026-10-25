// Exercise original Skiko/Skia exports without substituting JVM facade classes.
#include <clocale>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>

static void* symbol(void* library, const char* name) {
    void* result = dlsym(library, name);
    if (!result) { std::fprintf(stderr, "Missing native symbol: %s\n", name); std::exit(2); }
    return result;
}

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    void* library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) { std::fprintf(stderr, "%s\n", dlerror()); return 3; }
    using Create = int64_t (*)(void*, void*);
    using Empty = unsigned char (*)(void*, void*, int64_t);
    using GetMode = int (*)(void*, void*, int64_t);
    using SetMode = void (*)(void*, void*, int64_t, int);
    using Destroy = void (*)(void*);
    auto create = reinterpret_cast<Create>(symbol(library, "Java_org_jetbrains_skia_PathKt_Path_1nMake"));
    auto empty = reinterpret_cast<Empty>(symbol(library, "Java_org_jetbrains_skia_PathKt__1nIsEmpty"));
    auto getMode = reinterpret_cast<GetMode>(symbol(library, "Java_org_jetbrains_skia_PathKt__1nGetFillMode"));
    auto setMode = reinterpret_cast<SetMode>(symbol(library, "Java_org_jetbrains_skia_PathKt__1nSetFillMode"));
    auto finalizer = reinterpret_cast<Create>(symbol(library, "Java_org_jetbrains_skia_PathKt_Path_1nGetFinalizer"));
    int64_t path = create(nullptr, nullptr);
    if (!path || !empty(nullptr, nullptr, path) || getMode(nullptr, nullptr, path) != 0) return 4;
    setMode(nullptr, nullptr, path, 2);
    if (getMode(nullptr, nullptr, path) != 2 || !empty(nullptr, nullptr, path)) return 5;
    reinterpret_cast<Destroy>(static_cast<uintptr_t>(finalizer(nullptr, nullptr)))(reinterpret_cast<void*>(path));
    if (!std::setlocale(LC_CTYPE, "C.UTF-8")) return 7;
    using SupportsLocale = int (*)();
    auto supportsLocale = reinterpret_cast<SupportsLocale>(symbol(library, "XSupportsLocale"));
    if (!supportsLocale()) {
        std::fputs("SYNCWATCH_X11_LOCALE_UNAVAILABLE\n", stderr);
        return 8;
    }
    if (dlclose(library)) return 6;
    std::puts("SYNCWATCH_NATIVE_LINK_OK");
}
