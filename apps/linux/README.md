# SyncWatch Linux application

The Kotlin/Compose entry consumes the shared Apache-2.0 design package, restores local appearance preferences, opens the shared settings component and exposes the same six component-gallery launch arguments as the macOS and Windows clients. Window dimensions, theme values, component composition and localized copy come from `packages/design`.

The [application manifest](application.json) lists first-party inputs, required source-built components and blocked capabilities. `applicationBuildReady` is false: there is no qualified runnable Linux application package. The Compose/native/font source graph, registered Kotlin build and X11/Wayland video host remain required. The entry rejects local playback until the Linux native video window is implemented and accepted.

The required source/JVM check is:

```sh
python3 tools/jvm/jdk.py --provision
python3 tools/native/check_linux.py
```

This command exercises Java value/ownership boundaries and repository parity declarations. It does not compile or launch this Compose entry. Linux application acceptance requires the complete source build and a real desktop session; a remote desktop connection alone does not supply either.
