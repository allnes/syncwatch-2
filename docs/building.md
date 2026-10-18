# Building and running SyncWatch

These commands require this checkout and its declared source dependencies. The current native builds produce application shells; playback, synchronization, calling, and the complete shared-design interface are not yet integrated.

## Source checkout

```sh
git clone --recurse-submodules https://github.com/salo-group/syncwatch.git
cd syncwatch
git submodule update --init --recursive
```

External library sources are pinned under `3rdparty/`. The [dependency policy](architecture/dependencies.md) describes unresolved source graphs. Do not replace missing source dependencies with undeclared registry packages or floating revisions.

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

Both native test entry points also consume `contracts/fixtures/local-domain.json` beside the wire fixtures. They exercise local watch transitions and preference/resume persistence using only SDK libraries. The [local-state architecture](architecture/local-state.md) describes the API; these domain operations are not yet connected to the shell UI.

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
