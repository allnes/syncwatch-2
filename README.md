# SyncWatch

SyncWatch is a desktop application for watching local movies together with synchronized playback and Google Meet calls. It uses Swift on macOS, C# on Windows, VLC for playback, and Syncplay for synchronization.

[Project documentation](docs/README.md) defines application behavior, the shared design system, architecture, dependency policy, and build instructions.

External source dependencies are pinned Git submodules in `3rdparty/`:

```sh
git clone --recurse-submodules https://github.com/salo-group/syncwatch.git
cd syncwatch
git submodule update --init --recursive
```

The repository contains native shells in `apps/apple/` and `apps/windows/`, domain modules in `packages/apple-domain/` and `packages/windows-domain/`, the independent room service in `services/room-metadata/`, the platform-neutral design package, shared contracts in `contracts/`, pinned dependency sources, and validation/build tooling under `tools/`. See [building and running](docs/building.md) for declared toolchains and reproducible commands. Player, synchronization, call, and complete product UI integrations remain planned; the native shells are not yet the complete watch-together application.

The [application specification](docs/application.md) describes the library, player, settings, call window, and expected behavior. The [dependency policy](docs/architecture/dependencies.md) records pinned sources and unresolved source graphs. Product behavior is defined entirely in this repository.
