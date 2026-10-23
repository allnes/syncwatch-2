# Native playback

The local playback layer owns VLC independently of the interface, synchronization helper and room service. `packages/playback-native` is a small first-party C ABI compiled against the pinned public VLC headers. It dynamically opens the verified, source-built [media SDK](libvlc.md); it does not link to an installed VLC application.

## Ownership and observations

The Swift `VLCPlayback` actor and C# `VLCPlayback` dedicated worker serialize native operations outside the UI thread. The Linux development JVM boundary uses a bounded worker and first-party JNI adapter. Native callbacks only increment an atomic sequence; no callback enters managed code or updates a view. Consumers poll validated observations of the actual player clock, duration, pause state, seekability, tracks and output dimensions. Submitting a command does not acknowledge a changed player state.

A player belongs to one client run. Every replacement file advances its media generation; foreign runs, duplicate generations and stale commands or observations are rejected. Invalid loads do not consume a generation. Stop is idempotent and cannot resurrect a released media item. Close rejects new work, drains accepted requests and releases native callbacks, media, player, instance and owned library references.

Local files must have absolute paths. Network URIs are not accepted. Software decoding is the default until the selected hardware path has separately passed playback-control qualification. Volume, mute, track selection and drift-correction rate remain local operations. The synchronization coordinator will forward only the four authorized shared actions.

## Native surfaces and design

The macOS application retains its AppKit `NSView` and window until asynchronous native stop finishes. Windows uses an `HwndHost` in the design library's video slot. Unexpected removal parks its child HWND invisibly until native release finishes, then destroys the parked window. The shared design owns layout, colors, text, control placement and action validation; the playback code supplies observations and native resources.

The present player layout places its toolbar and footer outside the video rectangle. WPF popovers and future overlapping controls still require the architecture's separate owned overlay-window integration and DPI/focus acceptance. The development surface does not qualify those workflows, a physical display or speaker output. Linux JNI acceptance does not qualify the pending Kotlin/Compose GUI or its runtime dependency closure.

## Development entry

After building the application and the owned SDK, launch the macOS executable with:

```sh
SyncWatch.app/Contents/MacOS/SyncWatch --local-playback /absolute/movie.mkv
```

The default media location is `Contents/Frameworks/Media` inside the macOS bundle, or `Media` beside the Windows application. For an unbundled build use `--media-package /absolute/sdk/payload`; Windows also accepts `--playback-bridge C:\absolute\syncwatch_playback.dll`. This explicit entry enables local playback only. Normal Library/watch activation, shared selection, helper/player coordination, track/settings menus, previews and Meet integration retain their own implementation gates.

`--playback-report /absolute/report.json` runs actual AppKit/WPF acceptance against the authored four-second fixture and exits. It checks paused load, the advancing clock, pause stability, forward/backward seek observations, native surface creation, resizing and release. Windows `--playback-detach-probe` additionally exercises unexpected surface removal. Screen readback and physical output are reported separately; an unavailable capture does not imply presented-pixel acceptance.

## Validation and CI

On the native SDK host, run:

```sh
python3 tools/playback/build.py --package /absolute/sdk/payload --output /absolute/proof
python3 tools/playback/ci.py provision
python3 tools/playback/ci.py check --gui
```

The CI check uses `artifacts/dependencies/libvlc/<target>/payload`. Its default mode validates the C lifecycle, the real C#/JNI boundary where applicable, and native application compilation. `--gui` additionally requires a GUI host for the owned AppKit/WPF surface probes. The language probes exercise Unicode filesystem paths, generation transactions, actual pause and seek observations, tracks, bounded rate values, stale commands and repeated teardown. C# also checks cancellation before a queued command executes.

Each registered libVLC CI job retains a separate playback report and development candidate, including the complete owned SDK, original sources/grants, rebuild receipts and first-party source archive. Failed consumer diagnostics are retained and fail the job. Windows candidates require the pinned developer .NET runtime; Linux artifacts contain a development JNI boundary. These candidates are not signed, authenticated, immutable or release-ready installations.
