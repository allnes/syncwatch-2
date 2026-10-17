# External dependencies

All external library sources are pinned Git submodules under `3rdparty/`. `.gitmodules` defines upstream locations, and Git links define the exact revisions used by the product.

## Pinned source modules

| Submodule | Version / commit | Responsibility | Source license |
|---|---|---|---|
| `3rdparty/style-dictionary` | `v5.7.0` / `745264a62d01037581c6654fb4ac66bb3d245f07` | Generate platform resources from shared design data | Apache 2.0; `LICENSE` and `NOTICE` |
| `3rdparty/syncplay` | `v1.7.6` / `993232ab095bb810593459bc705b3e6fc64ad161` | Playback synchronization client engine and server | Apache 2.0; bundled files may have separate notices |
| `3rdparty/vlc` | `3.0.24` / `6de05adcbaf2e8b85fe86aad4169393098628119` | Embedded libVLC and C API headers | LGPL 2.1 in `COPYING.LIB`; the full application and individual modules have additional license terms |
| `3rdparty/fastjsonschema` | `v2.21.2` / `4f1ed6d9c0462f3522a66f49c8f3dc482300101b` | Offline Draft 7 contract validation from pinned Python source | BSD 3-Clause; `LICENSE` |
| `3rdparty/jvm-annotations` | `26.0.2` / `5ed7516e96eebef2a0cedc470d776b7351f52d6b` | JVM annotation classpath and named-module APIs | Apache 2.0; original license, repository declaration and source headers |
| `3rdparty/jbr-api` | `v1.9.0` / `bf95b3ebdadbb81c193fdf45b8947fb20163d5dc` | Optional JBR service interfaces in the planned desktop graph | Apache 2.0; full license, original headers and build-source change notice |

The Apache 2.0 requirement applies to the shared design library and Style Dictionary. It does not change VLC's license. The planned native adapters use Swift C interoperability and C# P/Invoke directly; VLCKit and LibVLCSharp are not included.

Style Dictionary is a build tool. The native UI does not require a JavaScript runtime for design resources. Its pinned `package.json` requires Node.js `>=22.0.0`; the source-only native build profile requires Node 24.3 or newer within 24.x for its built-in TypeScript compiler and synchronous module-resolution hooks.

The native design profile's 14 additional source submodules and complete selected dependency graph are recorded in [the component registry](../../tools/dependencies/components.json) and [package entry-point inventory](../../tools/design/sources.json). Sources are copied or compiled locally; registry packages and upstream prebuilt bundles are not used. The Node profile binds directly to the original Deepmerge/Glob sources and standard Node path API; browser wrappers and the unused default mergeability helper are not distributed. [Building the design tools](../design-generator.md) describes the supported Node configuration, source transformations, retained notices, and explicit exclusions for browser, ZIP, CLI, and web-format features. The [license inventory](../../tools/design/licenses.json) also covers notices for embedded source fragments.

The contract checker imports fastjsonschema directly from its submodule and verifies its revision, Git index pin, and source version. Its runtime graph has no third-party dependencies. Python 3.12 or newer is a developer/CI toolchain requirement. No pip packages are installed. The upstream nested JSON-Schema-Test-Suite submodule and development extras are unused by this checker. See the [tool manifest](../../tools/contracts/pyproject.toml) and [contract validation commands](contracts.md#reproducible-validation).

The same pinned validator is registered as a dependency-free Python source-package build in the [component registry](../../tools/dependencies/components.json). It provides a real Linux/macOS/Windows exercise for the shared source/cache infrastructure. It copies runtime Python sources and the BSD notice without invoking upstream packaging tools or development extras. See [source builds](../building.md#source-dependencies); this registration does not resolve the pending product-engine graphs below.

## Complete source graph

Every external library, including transitive dependencies, must have its source in a pinned submodule under `3rdparty/`. A top-level source checkout does not satisfy this rule for all of its dependencies. Registry packages and local caches do not replace source pins.

A source graph entry may declare an optional `exports` list of literal files or directories relative to its pinned submodule. The list is nonempty, sorted, unique and portable across platforms; overlapping or case-colliding roots are rejected. Every declared license/notice must be covered explicitly. Without this field, the entire upstream tree is snapshotted as before. Export roots and the verified snapshot digest are retained in build provenance and cache inputs, alongside the full revision and tree identity.

Selected snapshots must contain exactly the pinned Git blobs below those roots, preserving bytes, file types, symbolic-link targets and executable bits. Missing paths, `export-ignore` omissions, `export-subst` rewrites or missing notices fail preparation before compilation or cache reuse. Selection does not waive complete transitive-source or license review, change upstream pins, or replace component-specific source/API/license verification. It limits the snapshot passed to a trusted build recipe; it does not restrict that process's operating-system access.

Before building a component:

1. Resolve its complete runtime and build dependency graph for the selected configuration.
2. Record upstream URLs, exact revisions, licenses, and scope.
3. Add the corresponding source submodules and configure builds to use local sources.
4. Associate distributed binaries with their source revisions, build flags, toolchain, and SHA-256 digests.
5. Disable implicit dependency downloads and verify the notices for the resulting binary module set.

Compilers, platform SDKs, and system frameworks such as SwiftUI, AppKit, Foundation, WebKit, .NET, and WPF are build-platform requirements. This exception includes SDK-provided Swift Testing, compiler analyzers, formatting tools, and the .NET reference/runtime packs used by the dependency-free native shells. Toolchain versions and commands are declared in [building and running](../building.md); no NuGet test framework or formatter package is installed. Google Meet is a remote service rather than a vendored source library.

Python and Node.js are developer/runner toolchains. The CI artifact and dependency-cache adapters are first-party code using only Node built-ins; their local JavaScript actions run with the runner-provided Node 24 runtime. Their tests require Node 22 or newer. They install no npm packages or external Actions. The GitHub artifact service is remote infrastructure, used by the repository-owned workflows under `.github/workflows/` and not required by the application runtime.

## Dependency closure still required

The [annotations build](../jvm-annotations.md) uses only its pinned Java sources and the separately declared Temurin developer JDK. The JDK is a compiler SDK exception, with complete vendor legal files preserved and exact archive/installation hashes checked; it is not an application library or bundled JVM. This exception does not extend to the Kotlin standard library, Compose, Skiko/Skia, fonts or other JVM libraries. The annotations component runs its license/source/API verifier on cold builds and restored caches before success or distribution.

The [JBR API build](../jbr-api.md) uses this verified compiler SDK to build its own processor, compatibility plugin and optional-service interfaces from pinned sources. It has no external library dependency and includes no JBR runtime. The API's SDK module references do not clear packaging of a JVM. Its deterministic build-source modification, generated source, complete notices and artifacts are verified on cold builds and cache reuse.

| Component | Required source graph | Status |
|---|---|---|
| Headless Syncplay bridge | CPython, Twisted TLS, and the platform-specific transitive graph, including declared requirements such as `certifi` and `pem` | Versions and source submodules are not resolved yet |
| Design generator | Selected native Node source profile and transitive dependencies | Source graph and offline build are available for JSON/custom native formatters; browser/ZIP/CLI/web-format features are excluded |
| VLC build | Selected codecs, demuxers, filters, and other contrib libraries | Module selection and source graph are pending; implicit contrib downloads must be replaced with pinned sources |
| Windows Meet host | Open-source candidate: CEF, CefSharp, matching Chromium sources, and their dependencies | Browser-host compatibility and source closure are unresolved |
| Linux Compose UI | Selected Compose/AndroidX modules, Kotlin standard library, Skiko/Skia, enabled transitives and embedded code, plus any bundled fonts | Source graph, license inventory and offline build are pending; compiler/JDK/build-tool versions and any packaged runtime must be declared and reviewed separately |
| Linux Meet host | Application-owned browser with complete upstream and transitive sources | Host selection, source closure and actual Meet capabilities are unresolved |

This table describes the known areas of incomplete dependency closure. It is not a complete software bill of materials or a claim that offline builds are ready.

## Closed browser SDKs

WebView2's closed runtime and SDK cannot be represented by a source submodule; samples are not the library. It is excluded by the source dependency policy. CEF and CefSharp offer source access but do not establish Google authentication compatibility or Meet support by themselves.

## Working with submodules

Run from the repository root:

```sh
git submodule update --init --recursive
git submodule status --recursive
git diff --submodule=short
```

Each source update records an exact revision and the corresponding license/notice requirements. Reproducible builds must not use `git submodule update --remote`.

## Upstream references

- [Style Dictionary source and license](https://github.com/style-dictionary/style-dictionary).
- [Syncplay source and license](https://github.com/Syncplay/syncplay).
- [VideoLAN libVLC](https://www.videolan.org/vlc/libvlc.html).
- [fastjsonschema source and license](https://github.com/horejsek/python-fastjsonschema).
- [CEF](https://github.com/chromiumembedded/cef) and [CefSharp](https://github.com/cefsharp/CefSharp).
- [WebView2 runtime distribution](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution).

## Room metadata service

The metadata service uses the .NET/ASP.NET Core 10 shared framework, including Kestrel, JSON, cryptography, configuration, and WebSocket APIs. These are platform SDK/runtime dependencies under the SDK exception above. It installs no registry libraries. The server check uses the existing pinned fastjsonschema source for generated wire observations; Python is a developer/CI toolchain, not a service runtime. SDK archives for Linux x64, macOS arm64, and Windows x64 are pinned by SHA-512 in [the server toolchain manifest](../../tools/server/toolchains.json). See [build and run commands](../room-service.md).
