# Application architecture

SyncWatch is a native desktop product for synchronized local movie viewing and video calls. Native Swift/macOS and C#/WPF shells, local watch-state transitions, preferences, resume persistence, and an independent room metadata service are implemented. This document specifies the full application architecture; the shared Library workspace, application-settings dialog, core player chrome, player-settings and call shells and galleries consume a shared declarative component library; source-built headless Syncplay/TLS and development pipe transports are present; native VLC and application provider activation remain incomplete. The shells do not yet expose the domain workflows or connect to the room service.

## Technology decisions

| Area | Decision |
|---|---|
| Product platforms | macOS, Windows 11 x64, and Linux x64 |
| macOS client | Swift, SwiftUI, and AppKit for video surfaces and window management |
| Linux client | Kotlin/JVM with Compose Multiplatform Desktop; source/license closure precedes the application build |
| Windows client | C#, WPF, and .NET 10 LTS, with a small libVLC P/Invoke adapter |
| Shared design | Platform-neutral JSON tokens and component contracts in `packages/design`; Apache 2.0 Style Dictionary generates native resources |
| Playback | Embedded libVLC with SyncWatch controls |
| Synchronization | The upstream Syncplay client engine in a headless helper on each device, connected to a standard Syncplay server |
| Calling | Google Meet in a separate application-owned window; browser-host integration is not implemented |
| Room metadata | A C# / ASP.NET Core service over HTTPS/WSS for catalog and watch-session metadata |
| External libraries | Pinned source submodules under `3rdparty/`, including the complete transitive graph before component builds |
| Continuous integration | GitHub Actions for repository checks, native macOS/Windows builds, required Linux Kotlin-domain/JVM checks, reproducible dependencies, integration checks, and trusted release candidates |

The Windows SDK selection is pinned in [global.json](../../global.json) and the [toolchain manifest](../../tools/native/toolchains.json). See the [.NET support policy](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core). Additional Apple platforms require explicit decisions about process hosting, video surfaces, and call windows; macOS support does not imply iOS or tvOS support.

## Component topology

```mermaid
flowchart TB
    D[SyncWatch Design JSON] --> G[Style Dictionary build tool]
    G --> A[SwiftUI / AppKit client]
    G --> W[C# / WPF client]
    G --> L[Kotlin / Compose Desktop Linux client]
    L -. Source / build pending .-> CL[Linux coordinators and native adapters]
    CL -. Local movie .-> FL[Linux libVLC surface]
    CL -. Versioned local IPC .-> SL[Syncplay headless bridge]
    SL -. Syncplay protocol and TLS .-> SS
    CL -. HTTPS / WSS metadata .-> R
    CL -. Application-owned window .-> ML[Linux Meet host]
    ML -. Google web client .-> M
    A --> CA[Application coordinators and ports]
    W --> CW[Application coordinators and ports]
    CA --> VA[Native libVLC adapter]
    CW --> VW[Native libVLC adapter]
    VA --> FA[Local movie file]
    VW --> FW[Local movie file]
    CA <-->|Versioned local IPC| SA[Syncplay headless bridge]
    CW <-->|Versioned local IPC| SW[Syncplay headless bridge]
    SA <-->|Syncplay protocol and TLS| SS[Syncplay server]
    SW <-->|Syncplay protocol and TLS| SS
    CA <-->|HTTPS / WSS metadata| R[RoomMetadata service]
    CW <-->|HTTPS / WSS metadata| R
    CA --> MA[Application-owned Meet window]
    CW --> MW[Application-owned Meet window]
    MA <-->|Google web client| M[Google Meet service]
    MW <-->|Google web client| M
```

Each device reads its own movie file. Only play, pause, seek, and movie/playlist-item selection are shared user playback actions. RoomMetadata supplies the identities, ordering, membership, and authorization needed for them. Other application preferences and presentation state remain local. Google Meet handles calling independently; ending a call does not disconnect playback synchronization.

## State ownership

| Module or port | Responsibility and source of truth |
|---|---|
| LibraryService | Local catalog, authorized folder access, filesystem watching, and metadata cache; full paths stay local |
| MediaIdentity | Candidate matching, collision handling, and edition verification |
| WatchSessionCoordinator | Active media, generation, start/continue/end lifecycle, and application navigation |
| PlaybackPort | Media loading, pause, seek, rate, tracks, and local volume; actual VLC state is authoritative for observations |
| SyncPort | Syncplay connection, participants/readiness, allowed play/pause/seek actions, and local drift correction |
| RoomPort | Catalog exchange, media selection, session generations, missing media, Meet URI, and cross-channel participant binding |
| PreviewService | Separate bounded preview decoder and cache with cancellation; never changes the main player |
| CallPort | Call participation, first-join camera state, local preview, isolated output, shutdown, and verified capabilities; page load does not imply participation |
| SettingsService | Versioned local preferences, theme, language, playback settings, and schema upgrades |
| ConnectionSupervisor | Independent recovery of playback synchronization, metadata, and call channels |
| Design renderer | Displays state and emits user actions; contains no networking or media engine logic |

Swift and C# implement the [shared contracts](contracts.md) and use the same acceptance fixtures. The Kotlin Linux domain consumes that same corpus and protocol, including local watch generations and preference persistence. Domain behavior remains independent of UI and provider SDK types. The Python helper adapts the selected Syncplay engine while each application uses its selected desktop stack.

## Native video integration

On macOS, pass an AppKit `NSView` to `libvlc_media_player_set_nsobject`. Keep the view alive until rendering stops. Use an AppKit container and native window manager with SwiftUI controls. Validate compositing, clipping, fullscreen transitions, and hardware decoding.

On Windows, pass a native HWND to `libvlc_media_player_set_hwnd`. WPF controls cannot simply overlap another HWND because of airspace restrictions. The planned video host uses an owned overlay window for player controls and popovers, with coordinated position, DPI, focus, minimize, and fullscreen behavior. Validate this before implementing the full player UI. CPU-copy video callbacks require performance measurements before adoption for 4K playback. See [WPF technology regions](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/advanced/technology-regions-overview).

VLC image-adjustment APIs cover part of the image settings. Subtitle typography, external audio, audio normalization, and scaling still need working mappings for the selected module set. Some settings may require media reconfiguration. Every enabled control must have a verified effect. C API headers are in `3rdparty/vlc/include/vlc/`.

## Watch lifecycle

```mermaid
stateDiagram-v2
    [*] --> Library
    Library --> Preparing: Start watching
    Preparing --> Waiting: Media loaded and identity checked
    Waiting --> Watching: Syncplay readiness permits playback
    Watching --> Paused: Pause or synchronization loss
    Paused --> Watching: Accepted Syncplay state
    Watching --> Library: Return home and retain active session
    Library --> Watching: Continue active session
    Watching --> Ending: End watching
    Paused --> Ending: End watching
    Preparing --> Ending: Cancel or media failure
    Waiting --> Ending: Cancel or media failure
    Ending --> Library: Release local player and leave local watch
```

The watch and call lifecycles are separate. Returning home retains the active watch session. End releases local resources without an extra remote stop/close command. Membership bookkeeping must not become a fifth synchronized user action. Call audio is silent outside an active joined call and stops after hangup, close, or failed join. A new application launch may restore the last position, but it does not reactivate the previous session automatically.

Synchronization loss pauses playback and resets the rate to 1.0. Commands from an old generation are rejected. A call-only failure does not pause the movie. Metadata-only failure retains the agreed media but blocks operations that require a new shared selection.

## Source layout

Native shells, local domain modules, the room metadata service, the design package, documentation, contracts, validation tooling, workflows, and pinned submodules exist. Media/provider services and full product workflows in the layout below remain planned:

```text
apps/macos/                 # Swift application and native platform adapters
apps/windows/               # C# WPF application and native platform adapters
apps/linux/                 # Kotlin/Compose entry; registered application build pending
packages/design/            # Platform-neutral design data and component contracts
packages/macos-domain/      # Swift domain and use cases, independent of SwiftUI
packages/windows-domain/    # C# domain and use cases, independent of WPF
packages/linux-domain/      # Kotlin domain and atomic local persistence
contracts/                  # JSON schemas and shared acceptance fixtures
services/syncplay-bridge/   # Headless Python entry point and player/UI adapters
services/room-metadata/     # C# ASP.NET Core metadata service
tools/design/              # Custom Style Dictionary formatters
tools/dependencies/        # Source graph and deterministic build tooling
tools/ci/                  # Shared local/CI validation and orchestration
tools/contracts/           # Offline reference contract validation and tests
tools/native/              # Native SDK, formatting, build, and test entry points
tools/server/              # Server SDK provisioning, builds, transport and wire checks
.github/workflows/         # Repository, platform, dependency, integration, and release jobs
tests/                      # Planned integration coverage
3rdparty/                   # External source Git submodules
docs/                       # Application documentation and architecture
```

Dependencies point from UI to application to domain. Filesystem, VLC, Syncplay, and Meet integrations implement domain-facing ports. The design package does not import application services or domain logic.

## Linux client

The Linux client is implemented in Kotlin/JVM source with [Compose Multiplatform Desktop](https://github.com/JetBrains/compose-multiplatform#desktop). It runs on the JVM and uses Compose for its desktop UI. The existing JSON design source and wire contracts remain shared; macOS keeps SwiftUI/AppKit and Windows keeps C#/WPF.

Compose's JetBrains-owned code uses [Apache 2.0](https://github.com/JetBrains/compose-multiplatform/blob/master/license/README.md). The selected dependency graph still needs pinned source revisions and a complete license inventory before use. That inventory must cover the selected Compose/AndroidX modules, Kotlin standard library, Skiko/Skia rendering graph, transitive and embedded code, and any bundled fonts. Declare the compiler, JDK and build-tool versions separately; a packaged Java runtime also needs its own source, notice and distribution review. Neither a toolchain exception nor Compose's top-level license clears those artifacts. See [dependency policy](dependencies.md) and [licenses and distribution](../licenses.md).

Linux has a compiled Kotlin domain with the shared corpus and a registered source-built runtime, plus a Compose entry and shared renderer source. Its qualified Compose build, VLC desktop surface, helper/metadata application adapters and owned Meet host remain incomplete. X11 and Wayland require separate rendering, fullscreen, input, DPI, capture, and window-ownership checks, including any XWayland dependency. Google Meet remains the call provider. Compose does not select or verify a browser host; any candidate needs its own complete source/license graph and real Meet capability checks before adoption.

## Local data and permissions

Store versioned preferences and caches under Application Support on macOS and LocalAppData on Windows, using atomic writes. Store credentials in Keychain or protected Windows storage. Use an application-specific browser profile. Balance macOS security-scoped access for the lifetime of each media or folder operation.

Shared design assets contain no account, device, or room data. Catalog exchange sends only permitted media descriptors. A missing file does not trigger an upload. Audio controls affect only the intended movie or verified call output; system communications policy and other applications' volume remain outside the product's control.

## Integration limitations

| Component | Current limitation |
|---|---|
| Google Meet | Browser hosts, account access, media, native call controls, and capture shutdown are not implemented |
| VLC | macOS/Windows native surfaces and local development controls are implemented; Linux has a native/JNI boundary. Linux desktop video, overlays, timeline previews and complete player preferences remain incomplete |
| Dependencies | Complete transitive sources and offline builds for the product engines are unresolved |
| Syncplay bridge | Source-built headless runtime and development helper/native pipe adapters are present; actual VLC, authenticated installation and application provider activation remain incomplete; Kotlin transport is source-only |
| Shared design | Swift/WPF Library/Settings/core Player/PlayerSettings and galleries consume one declarative component tree through primitive adapters; native appearance preferences persist locally; Kotlin data and Compose Library/Settings/Player/PlayerSettings source are present with the Linux build still unavailable; call components and remaining player overlays remain planned |
| Linux client | Kotlin domain and source-built runtime pass the shared corpus in required CI; Compose entry and shared design source are present. Compose application build, native video window, GUI and calling remain incomplete |

These limitations distinguish the application architecture from the functionality available in the current shells.

## Related specifications

- [Application behavior](../application.md).
- [Building and running](../building.md).
- [Shared design system](design-system.md).
- [Shared contracts](contracts.md).
- [Local watch state and persistence](local-state.md).
- [Syncplay and room metadata](syncplay.md).
- [Room service API and ownership](room-service.md).
- [Google Meet integration](google-meet.md).
- [External dependencies](dependencies.md).

[Platform parity](platform-parity.md) defines the required three-client completion gate and current implementation matrix.
