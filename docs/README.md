# SyncWatch documentation

SyncWatch lets people watch their local movie files together with synchronized playback and a Google Meet call in a separate application-owned window.

## Application

- [Application behavior](application.md): screens, controls, settings, keyboard actions, window behavior, and connection recovery.
- [Running the room service](room-service.md): service setup, configuration, and startup.
- [Building and running](building.md): source checkout, declared toolchains, native builds, and launch commands.
- [Building the design tools](design-generator.md): source-only Style Dictionary profile and API.
- [Licenses and distribution](licenses.md): first-party licensing and third-party notices.

## Architecture and design

- [Application architecture](architecture/README.md): components, state ownership, native clients, and integration limitations.
- [Shared contracts](architecture/contracts.md): versioned schemas, wire units/bounds, ordering, IPC, and acceptance fixtures.
- [Local watch state](architecture/local-state.md): media ownership, Start/Continue/End, resume history, local preferences, and atomic persistence.
- [Shared design system](architecture/design-system.md): platform-neutral design contracts and generated native resources.
- [Room service API](architecture/room-service.md): authorization, catalog batches, snapshots, ordered events, and limits.
- [Syncplay and room metadata](architecture/syncplay.md): engine integration, local IPC, media selection, and reconnect behavior.
- [Google Meet integration](architecture/google-meet.md): application-owned call windows, authentication, capabilities, and browser-host limitations.
- [Dependencies](architecture/dependencies.md): pinned Git submodules and source dependency policy.

## Technology choices

| Area | Technology |
|---|---|
| macOS client | Swift, SwiftUI, AppKit |
| Linux client (planned) | C++20, Qt 6 Widgets, CMake; dependency closure and implementation pending |
| Windows client | C#, WPF, .NET 10 LTS |
| Shared design | `packages/design`, Apache 2.0, generated with Style Dictionary |
| Movie playback | VLC/libVLC |
| Playback synchronization | Syncplay |
| Calls | Google Meet in an application-owned window |
| Room metadata service | C#, ASP.NET Core, HTTPS/WSS |
| External source dependencies | Pinned Git submodules under `3rdparty/` |

Native application shells, domain ownership guards, generated design resources, and shared contracts are present. Native design renderers, player integration, synchronization, and calling are not yet complete. Application documentation describes the intended interface; the existing shells do not yet provide these workflows. Provider and dependency limitations are described in the architecture.
