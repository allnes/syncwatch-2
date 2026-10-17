# SyncWatch documentation

SyncWatch lets people watch their local movie files together with synchronized playback and a Google Meet call in a separate application-owned window.

## Application

- [Application behavior](application.md): screens, controls, settings, keyboard actions, window behavior, and connection recovery.
- [Building and running](building.md): source checkout, declared toolchains, native builds, and launch commands.
- [Product requirements](architecture/product-requirements.md): library, playback, synchronization, calls, settings, and resource lifecycle.

## Architecture and design

- [Application architecture](architecture/README.md): components, state ownership, native clients, and integration gates.
- [Shared contracts](architecture/contracts.md): versioned schemas, wire units/bounds, ordering, IPC, and acceptance fixtures.
- [Shared design system](architecture/design-system.md): platform-neutral design contracts and generated native resources.
- [Syncplay and room metadata](architecture/syncplay.md): engine integration, local IPC, media selection, and reconnect behavior.
- [Google Meet integration](architecture/google-meet.md): application-owned call windows, authentication, capabilities, and feasibility criteria.
- [Dependencies](architecture/dependencies.md): pinned Git submodules and source dependency policy.
- [Product acceptance](architecture/validation.md): behavior and integration conditions for a complete application.

## Technology choices

| Area | Technology |
|---|---|
| macOS client | Swift, SwiftUI, AppKit |
| Windows client | C#, WPF, .NET 10 LTS |
| Shared design | `packages/design`, Apache 2.0, generated with Style Dictionary |
| Movie playback | VLC/libVLC |
| Playback synchronization | Syncplay |
| Calls | Google Meet in an application-owned window |
| Room metadata service | C#, ASP.NET Core, HTTPS/WSS |
| External source dependencies | Pinned Git submodules under `3rdparty/` |

Native application shells, domain ownership guards, design data, and shared contracts are present. Native design renderers, the token generator, player integration, synchronization, and calling are not yet complete. The application specification describes required product behavior; it does not claim that the existing shells already implement it. Provider and dependency limitations remain explicit in the architecture.
