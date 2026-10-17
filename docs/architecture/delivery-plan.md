# Implementation plan

The product currently has architecture specifications, shared design data, and pinned top-level dependency sources. The deliverables below describe implementation work and its acceptance criteria.

The [pull request implementation plan](pull-request-plan.md) breaks these deliverables into PR01-PR24 and CI01-CI05 with explicit prerequisites, review scope, validation, and coverage of F01-F25. Establish repository CI first, then contracts, native shells, platform/dependency jobs, and call host sources before the early call experiment. Full call acceptance also requires the assembled playback and synchronization workflow. The [CI architecture](continuous-integration.md) defines automation and the boundary of hosted acceptance.

## Delivery sequence

| Stage | Deliverable | Acceptance criteria |
|---|---|---|
| P0: Continuous integration | Repository checks first, then native/dependency builds, integration jobs, and trusted candidate packaging | CI01-CI05 run actual checks for their supported scope; merge/release decisions distinguish hosted checks from physical/provider acceptance |
| P1: Call feasibility | Minimal application-owned Meet windows on macOS and Windows | Gate G1 covers account access, real two-way media, lifecycle, and required capabilities |
| P2: Reproducible dependencies | Pinned toolchains and complete component source graphs | All external libraries have source submodules; offline component builds and binary/source correspondence work |
| P3: Shared design | Style Dictionary formatters, Swift resources, C#/XAML resources, and component galleries | Deterministic generation, matching token IDs, dark/light themes, localized layouts, and reviewed interaction states |
| P4: Native playback | VLC video hosts, player controls, tracks, settings, and previews | Hardware decoding, Windows overlay/DPI/focus, fullscreen, preview isolation, and every exposed setting work |
| P5: Synchronization | Headless Syncplay bridge with a formal IPC contract | GUI-free initialization, standard-client interoperability, two-device recovery, bounded IPC, and safe child-process shutdown |
| P6: Room metadata | Catalog exchange, media identity, selection generations, missing-media handling, and Meet URI exchange | Room isolation, authorization, event ordering, snapshots, late join, and reconnect work without a second playback controller |
| P7: Product workflows | Library, Start/Continue/End, player, settings, and separate call shell | Functional requirements F01-F25 pass on both clients and meet visual acceptance |
| P8: Distribution | Signed macOS application and Windows package | Clean-machine startup, permissions, dependency notices, source/binary traceability, and complete shutdown |

Run the small call-host feasibility exercise before building the full UI. Resolve dependency closure for each executable component before its build. If a required provider capability is unavailable, keep the gap explicit and obtain a product decision before reducing scope.

Each completed deliverable receives focused validation, a commit, and a push. Split large stages into independently reviewable changes. Include validation commands and observed results in implementation reviews rather than adding a development diary to product documentation.

CI expands with each executable component rather than waiting for distribution. CI01 precedes PR01; CI02 and CI03 precede external component integration; CI04 precedes the complete user workflows; CI05 follows packaging and precedes final release acceptance.

## Engineering coverage

| Area | Required scenarios |
|---|---|
| Design generation | Unknown types, unresolved references, alpha values, logical units, stable ordering, repeated generation, and matching resource identifiers |
| Domain behavior | Repeated Start/Continue/End actions, paused seeks, generation changes, missing media, late join, conflicting selections, and cancellation |
| Bridge IPC | Version negotiation, partial frames, limits, duplicate IDs, write ordering, timeouts, foreign runs, EOF, and crashes |
| Room service | Authorization, room isolation, token expiry/revocation, event replay, snapshot gaps, reconnect, and bounded catalog batches |
| VLC integration | Actual seek completion, buffering, tracks, external assets, preview isolation, settings effects, and release callbacks |
| Native integration | Authorized filesystem access, focus, DPI, fullscreen, owned windows, settings persistence, and helper lifetime |

Add the test framework and reproducible build/test commands with the first executable component. Mocks are useful for contracts but do not establish codec, renderer, or provider compatibility.

## Physical-device acceptance

Use an interactive Apple Silicon Mac and a physical Windows 11 x64 device. Keep remote-access profiles, addresses, and credentials outside the repository. Install and pin the required SDKs through the declared development setup before building either client.

1. Prepare matching media fixtures on both devices: 1080p and 4K files with audio and subtitles. Identify each fixture by digest, codec, duration, and frame rate.
2. Verify library access, scanning, settings, themes, localization, and local playback before connecting the room.
3. Exercise play, pause, seek, competing actions, late join, missing/incompatible media, return home, Continue, and End from both clients.
4. Interrupt Syncplay, metadata, and the call independently. Reject obsolete actions after recovery.
5. Verify actual camera/microphone traffic in both directions, device selection, hangup, window restoration, and denied permissions. Remote-desktop device redirection does not replace physical-device acceptance.
6. Run playback and calling simultaneously. Measure playback positions, buffering, dropped frames, CPU/GPU use, resident memory, responsiveness, and time to first frame. Include a stop/start cycle.
7. Close and restart the application. Check for orphan helpers, hidden capture, unreleased access grants, and lost preferences.

The provisional drift target is p95 at or below 250 ms after stabilization. It is an engineering target, not a measured result or an upstream guarantee. Use a shared time basis with clock-offset and round-trip estimation. Measure seek, startup, and buffering intervals separately. Set resource budgets from comparable measurements on the supported hardware, media, and power settings.
