# Building and running SyncWatch

These commands require this checkout and its declared source dependencies. The current native builds produce application shells; playback, synchronization, calling, and the complete shared-design interface are not yet integrated.

## Source checkout

```sh
git clone https://github.com/salo-group/syncwatch.git
cd syncwatch
git submodule status
```

External library sources are pinned under `3rdparty/`. The [dependency policy](architecture/dependencies.md) describes unresolved source graphs. Do not replace missing source dependencies with undeclared registry packages or floating revisions.

Use Git 2.34 or newer and the component preparation commands below to initialize selected dependencies. Large upstream trees can contain unrelated test paths that exceed Windows limits; preparation applies reviewed sparse roots before checkout. Cloning all submodules recursively is unnecessary for these component builds.

## macOS

Use an Apple Silicon Mac, Xcode 16.3 or newer with its macOS SDK and command-line tools, and Swift 6.1 or newer. Swift language mode is 6 and the deployment target is macOS 13. The [toolchain manifest](../tools/native/toolchains.json) declares these requirements. Select the intended Xcode installation before building.

Run from the repository root:

```sh
python3 tools/native/check_apple.py
open artifacts/apple/SyncWatch.app
```

The entry point checks formatting, runs domain and native design tests, builds the SwiftUI executable, and assembles an unsigned application bundle with the checked-in Info.plist. SwiftPM uses local packages. Platform frameworks and Swift Testing come from the selected SDK.

The underlying build and domain-test commands are:

```sh
SYNCWATCH_CONTRACT_FIXTURES="$PWD/contracts/fixtures/acceptance.json" swift test --package-path packages/apple-domain -Xswiftc -warnings-as-errors
swift test --package-path packages/design -Xswiftc -warnings-as-errors
swift build --package-path apps/apple -Xswiftc -warnings-as-errors
```

## Windows

Use Windows 11 x64 and .NET SDK 10.0.402, as declared in [global.json](../global.json) and the [toolchain manifest](../tools/native/toolchains.json). SDK roll-forward and prerelease selection are disabled. The WPF application targets `net10.0-windows`; domain modules target `net10.0`.

Run from the repository root in Windows PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/native/check_windows.ps1
dotnet apps/windows/SyncWatch/bin/Debug/net10.0-windows/SyncWatch.dll
```

The execution-policy override applies only to that PowerShell process. For an isolated SDK, pass `-DotNet <sdk-directory>\dotnet.exe` to the checker and use that same executable to launch the application.

The checker restores local project references with [NuGet.Config](../NuGet.Config), checks formatting, builds with warnings as errors, and runs domain and compiled WPF resource checks. Registry sources are empty; external library packages are not downloaded. WPF, analyzers, and reference/runtime packs belong to the installed SDK.

Equivalent commands with the selected SDK are:

```powershell
dotnet restore SyncWatch.slnx --configfile NuGet.Config
dotnet format SyncWatch.slnx --no-restore --verify-no-changes
dotnet build SyncWatch.slnx --no-restore --configuration Debug
$env:SYNCWATCH_CONTRACT_FIXTURES = Join-Path $PWD 'contracts/fixtures/acceptance.json'
dotnet run --project packages/windows-domain/SyncWatch.Domain.Tests --no-build --no-restore --configuration Debug
dotnet run --project packages/design/tests/windows --no-build --no-restore --configuration Debug
```

Domain tests use an executable assertion harness; `dotnet test` is not their entry point. The framework-dependent application needs a compatible .NET Desktop Runtime. Closing its main window shuts down the WPF application.

Both native test entry points also consume `contracts/fixtures/local-domain.json` beside the wire fixtures. They exercise local watch transitions and preference/resume persistence using only SDK libraries. The [local-state architecture](architecture/local-state.md) describes the API. Native application settings use its preference store for language and theme; watch-session and resume operations still await their UI and media adapters.

The shells consume the committed resources in `packages/design/generated/`. Native builds need no Node runtime. After changing design inputs, use the [native resource generation commands](design-generator.md#native-resource-generation) and include the resulting resources in the change.

## Source dependencies

The [component registry](../tools/dependencies/components.json) and [build driver](../tools/dependencies/build.py) declare available source builds and target platforms:

```sh
python3 tools/dependencies/build.py check
python3 tools/dependencies/build.py plan
python3 tools/dependencies/build.py build --component fastjsonschema --platform macos-arm64 --cold
```

The ready components are the dependency-free fastjsonschema source package, the native Node design-generator profile, [JVM annotations](jvm-annotations.md), [JBR API](jbr-api.md) and the [Kotlin stdlib source package](kotlin-stdlib-sources.md), with `macos-arm64`, `linux-x64`, and `windows-x64` targets. The design tool requires Node 24.3 or newer within 24.x; see [building the design tools](design-generator.md). Binary JVM profiles require their explicitly provisioned, pinned developer JDK; the stdlib source package uses only Python and Git and enables no Kotlin compiler or binary. Media, synchronization, browser-host and full Linux Compose dependency graphs remain unavailable until their sources and real build recipes are registered. Outputs under `artifacts/` and caches under `.local/` are generated and ignored by Git.

Components may use [explicit source exports](architecture/dependencies.md#complete-source-graph) to snapshot reviewed files/directories from a pinned submodule, including all declared notices. Exported bytes are checked against Git before cold compilation or cache reuse. The annotations profile exercises this path on every supported build platform while retaining its reviewed JAR digests. Run the dependency infrastructure regression tests with `python3 -m unittest discover -s tools/dependencies/tests -v`.

## Source and contract validation

Repository checks require Git, Python 3.12 or newer, and Node.js 22 or newer. Contract validation imports only the pinned validator source:

```sh
python3 tools/ci/check_repository.py
git submodule update --init --checkout --depth=1 -- 3rdparty/fastjsonschema
python3 tools/contracts/check_contracts.py
```

A successful shell build or source check does not establish functioning media, synchronization, calling, visual conformance, signing, or release readiness. The [architecture](architecture/README.md#integration-limitations) describes the current integration limitations.


## Library component gallery

The macOS and Windows shells display the shared Library workspace with unavailable service actions disabled. Launch the fixture gallery to select visual state, theme and language:

```sh
artifacts/apple/SyncWatch.app/Contents/MacOS/SyncWatch --design-gallery
```

```powershell
apps/windows/SyncWatch/bin/Debug/net10.0-windows/SyncWatch.exe --design-gallery
```

The gallery uses synthetic media entries and emits presentation actions only. It does not scan folders, start VLC, synchronize playback or call Google Meet. Native checks save the state/theme/language/viewport matrix under `artifacts/design/apple/` or `artifacts/design/windows/`; CI includes it in the corresponding native artifact. The Kotlin data and Compose renderer source are present in `packages/design/`, but a Linux application build remains blocked on dependency/compiler/native/license closure.


## Application settings

In a normal native launch, use **Settings** in the Library header. Change the language or theme and choose **Save** to persist the change and apply it immediately. **Cancel** discards unsaved edits. Settings use the application-owned `SyncWatch/local-state.json` under Application Support on macOS and Local Application Data on Windows. Existing media/resume preferences are retained. Files from a newer format are left unchanged and the dialog becomes read-only. Library, call and connection settings remain unavailable until their adapters exist.

For fixture-only review, launch the same native executable with `--settings-gallery` instead of `--design-gallery`. The Settings gallery switches section, theme, language and visual state and can simulate a failed save. It does not read or write application preferences. Linux has matching first-party metadata/renderer source, with no runnable Settings gallery until its build prerequisites are complete. Native validation retains 224 images per platform: 40 Library, 48 Settings, 56 Player and 80 PlayerSettings renders.


## Player component gallery

Launch the native executable with `--player-gallery` to inspect the shared player chrome. The gallery selects seven visual states, dark/light themes and English/Russian copy. It uses a long fixture title and explicit synthetic observations; user requests update only the fixture. It does not open media, initialize VLC, synchronize playback, join a call or load normal application preferences.

The reusable `PlayerChrome` accepts an owned video-surface slot and presentation observations/capabilities. It renders the compact toolbar, central previous/skip/play-pause/skip/next controls, timeline, local movie volume and mute. Track menus and playlist stay disabled until their components/adapters exist. The gear opens PlayerSettings inside the fixture gallery. Return-to-library, end, call and fullscreen are presentation requests for the caller; the gallery records them without operating a native window or provider. The normal Library cannot enter an unimplemented playback session.

Native tests exercise shared boundary fixtures, WPF control input, observation updates without echoed seeks, and fixed logical viewports at 1120×760 and 800×600. The image matrix includes 56 Player renders per platform. Kotlin has matching first-party source, with no compiled/rendered Linux player until the declared Linux build prerequisites pass. Keyboard shortcuts, fullscreen/window ownership, overlays above real video, physical display scales and media/provider behavior require integration acceptance.


## Player settings gallery

Launch the native executable with `--player-settings-gallery` to inspect playback, subtitles, image, audio and advanced sections in the compact dialog. Select editing, saved, invalid or read-only state and enable **Fail save** to exercise a failed acknowledgement. Save succeeds only when the caller accepts the complete valid draft. Reset changes editable fields in the selected section; Cancel discards changes since the last successful save.

The gear in `--player-gallery` opens the same component and retains acknowledged values for that gallery instance. Only fixture skip/default-volume observations are updated. The subtitle preview draws native text from the current draft. These galleries do not read/write normal preferences, initialize VLC, apply real image/audio/subtitle filters, synchronize playback or start calls. Normal application playback awaits its adapters. Linux has matching first-party source, with no executable gallery until dependency/compiler/native/font/license prerequisites pass.


## Declarative component library

Screen composition, responsive rules, styles and primitive appearance are declared in `packages/design/layouts.json`; tokens and form/action metadata remain in the same Apache-2.0 package. Regenerate committed native data with the [design generator](design-generator.md#native-resource-generation) after changing the document. Application/presentation bindings consume the component by name and do not specify another native layout.

Resource generation and repository validation run the design-isolation check. Native validation also renders the same axis/order/spacing probe document through the actual SwiftUI/WPF adapters and verifies stable WPF inputs when observations or list contents change. Existing model, persistence, capability and image-matrix checks still run. Linux checks cover shared data/tooling and matching first-party source until its complete application build is available.


## Call component gallery

Launch the native executable with `--call-gallery` to inspect the compact call shell, remote/self-view slots and call/window controls. Choose a host/preview case, English or Russian, and a dark or light theme. The gallery simulates microphone, camera, volume, pin/fullscreen/minimized and closed observations in memory. Move/resize requests are recorded; the gallery does not operate an OS call window.

The shell enables media controls only after explicit joined observations and capabilities are supplied. Missing camera content stays a placeholder. These fixtures do not access normal preferences, open Google Meet, initialize a browser, request device permission or start/stop capture/audio. The Linux renderer/gallery remains source-only until its complete dependency/compiler/native/font/license build is available.


## Selection-menu component gallery

Launch the native executable with `--selection-menu-gallery` to review playlist, audio-track and subtitle menus. Choose a menu kind, empty/available/read-only/long-list case, theme and language. Selection updates only the gallery's in-memory fixture and records the correlated request. It does not read preferences, select real media/tracks or contact a provider. Normal player track/playlist actions remain unavailable until their integration supplies capabilities.

Native checks add 48 menu renders per platform to the required artifact matrix. The common input corpus verifies identity/revision, action scopes, invalid observations and UTF-8 bounds through the generator, Swift and C#. Actual WPF controls verify input-free observation refresh, selection requests and long-list scrolling. Linux carries matching data/model/renderer/gallery source; it has no runnable gallery until compiler/Compose/native/font/license closure passes.
