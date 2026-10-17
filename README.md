# SyncWatch

SyncWatch is a desktop application for watching local movies together with synchronized playback and Google Meet calls. It uses Swift on macOS, C# on Windows, VLC for playback, and Syncplay for synchronization.

[Project documentation](docs/README.md) defines the product requirements, shared design system, architecture, dependency policy, and implementation plan.

External source dependencies are pinned Git submodules in `3rdparty/`:

```sh
git clone --recurse-submodules https://github.com/allnes/syncwatch-2.git
cd syncwatch-2
git submodule update --init --recursive
```

The repository currently contains architecture specifications, the platform-neutral design package, and pinned dependency sources. Application implementation and runtime validation are pending.
