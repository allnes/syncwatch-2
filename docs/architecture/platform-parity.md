# Desktop platform parity

SyncWatch has three required desktop clients: macOS, Windows and Linux. First-party platform directories use `macos`, `windows` and `linux`. Shared code, contracts, services and design declarations remain independent of those directories. Apple framework names and native SDK target identifiers retain their original names.

Each feature slice covers application ownership, domain behavior, persistence, shared design consumption, native providers and validation on every applicable client. A slice is complete only after all three implementations and their required native acceptance pass. Source-only renderers, developer compiler experiments, JNI tests and successful server builds do not establish an application or GUI result.

The [desktop acceptance matrix](../testing/desktop-acceptance.md) requires visible native windows on all three targets and all six directed sender/observer combinations for synchronization.

The [platform registry](../../tools/native/platforms.json) records implementation directories and per-feature validation. Repository validation requires all three module sets, rejects empty implementation directories, requires all three CI lanes in the aggregate, and rejects a completed feature with source, research or native-boundary-only validation. These checks validate structure and declarations; source review and actual acceptance remain required.

| Feature | macOS | Windows | Linux |
|---|---|---|---|
| Watch domain and local preferences | Native implementation and shared corpus | Native implementation and shared corpus | Compiled Kotlin domain, source-built runtime and the same shared corpus |
| Library and settings application | Swift application, native folder grants and persistent local state | C# application, native folder picker and persistent local state | Kotlin/Compose application, native folder picker and persistent local state |
| Shared component galleries | Native renders and shared pixel probes | Native renders and shared pixel probes | Compiled Compose/Skia presentation checks and shared pixel probes; full interactive gallery acceptance remains separate |
| VLC local controls and native video | AppKit surface and ordinary local playback | Owned HWND surface and ordinary local playback | Owned X11 child, ordinary playback and fullscreen; complete DPI/focus coverage remains open |
| Owned Syncplay helper transport | Swift pipes and normal shared-watch coordinator | C# pipes and normal shared-watch coordinator | Kotlin pipes and normal shared-watch coordinator |

The watch domain and local-preferences slice is qualified across the three native clients. Its [Kotlin runtime build](../kotlin-stdlib.md) compiles and executes the Kotlin domain corpus on Linux, including restored-cache verification. Swift runs only on macOS and C# only on Windows.

All three clients have source-built application packaging paths under `tools/application`. Linux compiles production Kotlin/Java inputs against verified Compose dependencies and packages its own source-built JVM, Skiko renderer, VLC, X11 clients and Syncplay helper. Native desktop qualification has exercised folder restoration, local playback, fullscreen, ordinary room Join/Start, all six directed Play/Pause/Seek paths, metadata-service loss, End and offline Leave. These scenario results do not complete every feature slice or qualify every display environment.

Linux aggregate readiness remains false in [its build manifest](../../apps/linux/application.json). This conservative declaration is gated by the complete registered source-component statuses and remaining application acceptance. It does not mean that the Linux window or production package is absent. `tools/native/check_linux.py` is the narrower Kotlin-domain/JVM-boundary check: its `applicationBuilt: false` and `guiAccepted: false` describe that command's scope. The separate production build, package inventory and visible desktop evidence must be assessed independently. Likewise, [Linux design assertions](../../packages/design/tests/linux/README.md) establish presentation behavior and shared geometry; offscreen renders alone cannot qualify an interactive desktop workflow.

The [source-built Compose runtime](../compose-runtime.md) supplies composition and retained-state semantics for Linux UI work. Its compiler-transformed consumers remain prerequisites to application acceptance. Platform consumer checks run on their native targets: Swift on macOS, Kotlin on Linux and C# on Windows. Shared design values stay in the Apache-2.0 Design declarations.

The [composition state profile](../compose-state.md) supplies lifecycle and in-process state recreation on Linux's Swing event thread. It remains independent of domain persistence and shared design. Complete settings behavior, reconnect recovery, display-environment coverage and the remaining product scenarios still require acceptance; successful module checks and selected desktop scenarios do not establish full parity or Practical Product Readiness.
