# Desktop platform parity

SyncWatch has three required desktop clients: macOS, Windows and Linux. First-party platform directories use `macos`, `windows` and `linux`. Shared code, contracts, services and design declarations remain independent of those directories. Apple framework names and native SDK target identifiers retain their original names.

Each feature slice covers application ownership, domain behavior, persistence, shared design consumption, native providers and validation on every applicable client. A slice is complete only after all three implementations and their required native acceptance pass. Source-only renderers, developer compiler experiments, JNI tests and successful server builds do not establish an application or GUI result.

The [platform registry](../../tools/native/platforms.json) records implementation directories and per-feature validation. Repository validation requires all three module sets, rejects empty implementation directories, requires all three CI lanes in the aggregate, and rejects a completed feature with source, research or native-boundary-only validation. These checks validate structure and declarations; source review and actual acceptance remain required.

| Feature | macOS | Windows | Linux |
|---|---|---|---|
| Watch domain and local preferences | Native implementation and shared corpus | Native implementation and shared corpus | Compiled Kotlin domain, source-built runtime and the same shared corpus |
| Library, settings and component galleries | Compiled native components | Compiled native components | Compose components and application entry source; application build pending |
| VLC local controls and native video | AppKit surface | Owned HWND surface | Source-built native/JNI boundary; desktop surface pending |
| Owned Syncplay helper transport | Executed Swift pipes | Executed C# pipes | Kotlin transport source; full application integration pending |

The watch domain and local-preferences slice is qualified across the three native clients. Its [Kotlin runtime build](../kotlin-stdlib.md) compiles and executes the domain corpus on each supported developer host, including restored-cache verification.

Linux application readiness is explicitly false in [its build manifest](../../apps/linux/application.json). The required Linux CI lane compiles the Kotlin domain and executes the shared corpus and JVM boundary checks and retains `applicationBuilt: false` and `guiAccepted: false`. UI and video slices remain unqualified. The remaining Compose/Skiko/Skia/native/font source graph, actual desktop window, shared render matrix and native video lifetime must be completed before Linux GUI acceptance.

The [source-built Compose runtime](../compose-runtime.md) supplies composition and retained-state semantics for that Linux UI work. Its compiler-transformed headless consumer and cold/cache checks run on all three developer targets. It does not change the application/gallery/video qualification above or introduce platform-specific design values.
