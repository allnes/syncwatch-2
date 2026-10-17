# SyncWatch

Native successor to the SyncWatch prototype: Swift on Apple platforms, C# on Windows, VLC playback, Syncplay synchronization, and Google Meet calls.

[Project documentation](docs/README.md) contains the architecture, prototype inventory, dependency policy, and implementation plan. Locally, the same documentation is available at `/Users/anesterov/repos/salo-syncwatch/docs`.

External source dependencies are pinned Git submodules in `3rdparty/`:

```sh
git clone --recurse-submodules https://github.com/allnes/syncwatch-2.git
cd syncwatch-2
git submodule update --init --recursive
```

This is currently an architecture repository. Application build and runtime validation have not been implemented.
