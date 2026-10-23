# SyncWatch

SyncWatch is a desktop application for watching local movies together with synchronized playback and Google Meet calls. It uses Swift on macOS, C# on Windows, Kotlin/JVM with Compose on Linux, VLC for playback, and Syncplay for synchronization.

[Project documentation](docs/README.md) defines application behavior, the shared design system, architecture, dependency policy, and build instructions.

External source dependencies are pinned Git submodules in `3rdparty/`:

```sh
git clone https://github.com/salo-group/syncwatch.git
cd syncwatch
git submodule status
```

Use the component preparation commands in [the build guide](docs/building.md#source-dependencies) to initialize the selected source dependencies. They apply sparse checkout before materializing large upstream repositories, including on Windows.

The repository contains native shells in `apps/macos/`, `apps/windows/` and `apps/linux/`, domain modules in `packages/macos-domain/`, `packages/windows-domain/` and `packages/linux-domain/`, the independent room service in `services/room-metadata/`, the platform-neutral design package, shared contracts in `contracts/`, pinned dependency sources, and validation/build tooling under `tools/`. See [building and running](docs/building.md) for declared toolchains and reproducible commands. Player, synchronization, call, and complete product UI integrations remain planned; the native shells are not yet the complete watch-together application.

The [application specification](docs/application.md) describes the library, player, settings, call window, and expected behavior. The [dependency policy](docs/architecture/dependencies.md) records pinned sources and unresolved source graphs. Product behavior is defined entirely in this repository.

[Desktop platform parity](docs/architecture/platform-parity.md) records the three-client implementation and acceptance boundary. Linux carries an application entry and domain implementation; its complete source build, GUI and native video surface remain unqualified. Features are not complete while a required client is missing its implementation or acceptance.
