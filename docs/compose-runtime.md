# Source-built Compose JVM runtime

The `compose-runtime` component builds six runtime modules using the same offline recipe on macOS ARM64, Windows x64 and Linux x64. It includes JSpecify 1.0.0, AndroidX annotation 1.9.1, AndroidX collection 1.5.0, Compose runtime-annotation 1.12.1, runtime 1.12.1 and runtime-retain 1.12.1. The parent [concurrency profile](jvm-concurrency.md) supplies the owned Kotlin standard library, annotations, Atomicfu and coroutines.

Every application library comes from a pinned Git submodule under `3rdparty`. The [source profile](../tools/jvm/compose_runtime.json) lists the exact selected files, hashes, versions, module ownership and common/intermediate/JVM refinements. Google runtime sources are selected from the AndroidX release commit; JetBrains metadata redirects do not introduce another runtime implementation. Original Kotlin/Java files remain unchanged, including the embedded immutable collections and their original copyright headers. All new selections use Apache-2.0. The source archive retains complete original files and notices, original build declarations and the owned profile. Parent grants remain covered by their existing profiles.

The Kotlin 2.3.20 SDK's Compose compiler plugin transforms only the runtime, retain and consumer compilation. Its separate [compiler policy](../tools/jvm/compiler_plugins.json) binds the exact SDK file digest and matching source revision to compiler-process-only use. Plugins are disabled by default; callers select an approved policy name. Raw plugin paths/options and all SDK runtime/annotation/reflect JARs remain excluded from target inputs and distributions. The SDK inventory and vendor notices are unchanged.

JSpecify follows its original Java 8 source/target build with the newer JDK annotation APIs and original Java 9 module descriptor. This is a qualified JDK 21 developer runtime, not Java 8 runtime acceptance. Collection's original JVM Java bridge is compiled after Kotlin resolution; the common-only runtime annotation module has an explicitly empty JVM leaf. No Gradle, Maven, binary library download, generated stub or source patch runs during the build.

```sh
python3 tools/dependencies/build.py prepare --component compose-runtime --platform linux-x64
python3 tools/jvm/jdk.py --provision
python3 tools/jvm/kotlin.py --provision
python3 tools/dependencies/build.py build --component compose-runtime --platform linux-x64 --cold
python3 tools/dependencies/build.py build --component compose-runtime --platform linux-x64
```

Use `macos-arm64` or `windows-x64` on the corresponding host and `python` on Windows. Preparation and explicit SDK provisioning may access the network. Compilation and cache verification consume only reviewed local inputs. Cold builds and cache reuse check exact target binary hashes, all originals/notices and the complete parent runtime. The consumer compiles real composable code with the approved plugin, verifies transformed signatures and all ten runtime code origins, and executes collections, conflicting snapshots, keyed node moves/updates, remember/disposal, retained-object ownership and normal recomposer shutdown in a Unicode working directory.

The Windows developer host requires Win32 long-path support (`LongPathsEnabled = 1`) for Python source staging; original Compose filenames exceed the legacy 260-character limit. The builder enables Git's long-path handling consistently for checkout and source inspection. This is a developer build prerequisite, not a change to product filenames or distributed source bytes.

Completion waits for the tested composition's `SideEffect`, then inspects its node tree. In the selected runtime, a retained-store frame-end callback can leave `Recomposer.currentState` at `PendingWork` after applying a frame; `awaitIdle` is therefore not used as this scenario's completion signal. This does not qualify general idle-state reporting. The implementation remains unmodified.

This component supplies the headless composition runtime. The separate [composition state profile](compose-state.md) adds runtime-saveable, saved-state/lifecycle support and a real Swing Main dispatcher. Compose UI, Skiko/Skia, native/font closure, an owned desktop window, shared galleries and VLC desktop surface acceptance remain required. The Linux application manifest keeps `applicationBuildReady: false`; no GUI or application acceptance follows from this build.
