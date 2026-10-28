# SyncWatch Linux application

The Kotlin/Compose entry consumes the shared Apache-2.0 design package, restores local appearance preferences, opens the shared settings component and exposes the same six component-gallery launch arguments as the macOS and Windows clients. Window dimensions, theme values, component composition and localized copy come from `packages/design`.

The normal application owns Library, local playback, room membership and the shared-watch coordinator. Native X11 video, fullscreen, local track menus, room Join/Start and all six directed Play/Pause/Seek paths have been exercised with packaged macOS, Windows and Linux peers. Each scenario still needs its own current acceptance; remaining settings, reconnect and display coverage prevent a whole-product readiness claim.

The [application manifest](application.json) lists first-party inputs, required source-built components and remaining qualification gates. Its conservative `applicationBuildReady: false` is tied to aggregate source-component readiness and complete acceptance. A production Linux build and package exist independently of that aggregate declaration. See [desktop platform parity](../../docs/architecture/platform-parity.md) for the distinction.

The required Kotlin domain/JVM check is:

```sh
python3 tools/jvm/jdk.py --provision
python3 tools/jvm/kotlin.py --provision
python3 tools/dependencies/build.py build --component kotlin-stdlib --platform linux-x64
python3 tools/native/check_linux.py
```

These commands compile the Kotlin domain against the source-built standard library, execute the shared domain corpus, and check Java value/ownership boundaries and repository parity declarations. This narrow check does not compile or launch the Compose entry. `tools/application/build_linux.py` builds declared production inputs using explicit verified toolchain and desktop SDK paths; `tools/application/package.py` assembles the private runtime closure. A successful build or remote desktop connection does not replace acceptance in the actual application window.

The [source-built concurrency component](../../docs/jvm-concurrency.md) supplies Atomicfu and coroutines as Compose prerequisites. Source-build receipts and Linux runtime consumers remain separate from application/GUI acceptance:

```sh
python3 tools/dependencies/build.py build --component kotlinx-concurrency --platform linux-x64
```
