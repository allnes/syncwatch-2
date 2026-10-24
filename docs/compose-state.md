# Desktop composition state and lifecycle

The `compose-state` component builds nine modules from pinned Git submodules using the same offline recipe on macOS ARM64, Windows x64 and Linux x64. It supplies the state and lifecycle prerequisites for the Linux desktop client. Its parent [Compose runtime](compose-runtime.md) supplies the ten existing owned JVM libraries.

| Module | Selected version | Responsibility |
|---|---|---|
| AndroidX arch-core-common | 2.2.0 | Lifecycle collection support |
| Kotlin serialization core | 1.7.3 | Generated serializer runtime |
| Kotlin coroutines Swing | 1.11.0 | Real Swing event-thread Main dispatcher |
| AndroidX lifecycle-common, lifecycle-runtime, lifecycle-runtime-compose | 2.11.0 | Lifecycle state, task cancellation and composition integration |
| AndroidX savedstate, savedstate-compose | 1.4.0 | Owner-scoped registry and structured state codec |
| Compose runtime-saveable | 1.12.1 | Positional remembered-state save and restore |

The [source profile](../tools/jvm/compose_state.json) records every selected file, digest, source revision, module, resource, original Java 9 descriptor and common/intermediate/JVM refinement. The six added source selections use Apache-2.0 and retain their complete original grants, build declarations and source headers, including the explicitly inventoried repository-licensed declarations without individual headers. The source archive retains original bytes and the owned profile. Each binary carries original notices and a prominent build-profile notice. No source patch, prebuilt application library, Maven or Gradle download is used.

Saveable and Swing have separate source submodules at exactly the same upstream revisions as their respective parent Compose runtime and coroutines sources. They select disjoint modules; they introduce no second runtime implementation or version. The existing parent source inventories and binary pins remain unchanged. Arch-core uses the original AndroidX Google Git repository for its historical release commit.

Serialization retains its original runtime version and minimum Kotlin version manifest fields. Its original ProGuard/R8 rules, Swing's original Main dispatcher service declaration and both original Java 9 descriptors are built or copied from the reviewed sources. The Kotlin SDK's [named compiler policy](../tools/jvm/compiler_plugins.json) permits Compose and serialization plugins only inside the compiler process. Both are disabled unless explicitly selected. SDK runtime, annotation and reflection JARs remain excluded from target inputs and distributions.

```sh
python3 tools/dependencies/build.py prepare --component compose-state --platform linux-x64
python3 tools/jvm/jdk.py --provision
python3 tools/jvm/kotlin.py --provision
python3 tools/dependencies/build.py build --component compose-state --platform linux-x64 --cold
python3 tools/dependencies/build.py build --component compose-state --platform linux-x64
```

Use the corresponding target and Python command on macOS or Windows. The same JDK, Kotlin SDK and Windows long-path prerequisites as the parent runtime apply. Preparation and explicit SDK provisioning can access the network. Build and restored-cache verification consume only local reviewed inputs, recheck all nineteen owned runtime libraries, exact binary pins, original sources, resources, notices and parent payloads. Required CI includes all three dependency targets and the cache-tampering regressions.

The first-party [state owner](../packages/linux-state/src/syncwatch/state/CompositionStateOwner.kt) owns one future desktop window's lifecycle and saveable registry. The window host must create, resume, stop, snapshot and close it on the Swing event thread, save while its composition providers are alive, and dispose those compositions before closing the owner. The composition provider installs lifecycle, saved-state and saveable locals; it never owns the window lifetime. The host supplies the supported saved-value policy, and content supplies explicit savers for values outside it.

`CompositionSnapshot` is opaque in-process recreation state confined to the same event thread. It is not a disk format, cross-thread message or replacement for the domain's durable local-preferences store. Closing is idempotent, moves the lifecycle to destroyed, and rejects later mutation or snapshot requests.

The compiler-transformed consumer compiles this actual first-party module with both named plugins in a Unicode working directory. It verifies all nineteen library origins, a generated serializer with nested Unicode data, the real Swing/Main dispatcher, owner and lifecycle thread checks, repeated lifecycle start/stop and cancellation on destruction, lifecycle-aware flow collection, all owner locals, remembered counter/model restoration, one-shot saved-state provider consumption and observer/composition/recomposer shutdown. It runs headlessly on the real event thread without a substitute dispatcher or rendered window. The test driver owns its frame clock and global snapshot notification pump, and closes both with its coroutine scope; a rendered UI must supply its own integration.

This qualifies state ownership and the source-built dependency profile. The owner is not yet attached to a desktop window. Compose UI, Skiko/Skia, native/font closure, compiled galleries, native video lifetime and full Linux application acceptance remain required. The Linux application manifest keeps `applicationBuildReady: false`. macOS and Windows retain their existing native application ownership; no product feature or design value is added ahead of Linux parity.
