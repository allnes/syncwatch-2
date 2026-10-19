# Native compression dependency

The `zlib` component builds pinned zlib 1.3.2 as a static native library for macOS arm64, Windows x64 and Linux x64. It is a prerequisite for assembling the embedded CPython runtime. The application does not yet load that runtime, and `syncplay-runtime` remains unavailable.

All external sources come from the Git submodule `3rdparty/zlib`. The selected export contains the original upstream CMake configuration, 15 library translation units, their headers and full notices. Contrib implementations, bindings, assembly alternatives, example executables, installation and shared libraries are disabled. The selected build uses only the platform C/OS SDK in addition to these sources; it does not discover or link an installed system zlib.

## Developer SDKs

Use Python 3.12 or newer, CMake 3.30 through 4.x and the installed platform C compiler/build SDK. These are developer tools, not application libraries or packaged runtimes:

| Host | SDK |
|---|---|
| macOS arm64 | Xcode command-line tools with clang, ar, make and macOS SDK; deployment target 13.0 |
| Windows x64 | Visual Studio 2022 x64 C tools (v143) and Windows 10/11 SDK |
| Linux x64 | Native C compiler, ar and make |

CMake may be on PATH, in its standard macOS installation, or in an isolated developer SDK under the toolchain directory. The build does not install SDKs or change system configuration. The SDK probe records CMake/compiler identities and executable digests, platform SDK and selected build tools in dependency inputs/cache keys. No CMake, compiler, redistributable runtime or test executable is copied into the library payload.

## Build and verify

Run on the corresponding host; a target flag cannot turn a foreign host into a native builder:

```sh
python3 tools/dependencies/build.py build --component zlib --platform macos-arm64 --cold
python3 tools/dependencies/build.py build --component zlib --platform macos-arm64
python3 tools/compression/zlib_build.py verify --platform macos-arm64
python3 -m unittest discover -s tools/compression/tests -v
```

Use `windows-x64` or `linux-x64` for the other hosts. The first build compiles the exact selected original source twice in separate build directories and requires identical static library bytes and probe results. A cache hit still configures from verified source, checks every original/generated header, source archive, notice and SDK report, then compiles a fresh independent probe against the restored static archive and executes it. Original source/checksum mismatches, unexpected payload files, wrong versions/architectures and native failures reject the artifact.

The probe exercises round trips, output bounds, truncated input, corrupt checksums, known CRC/Adler values, raw DEFLATE, gzip streams, preset dictionary and gzip file close/removal. Its input/output buffers and execution deadline are bounded; it accesses only its owned synthetic file and starts no provider or network connection. These checks are not a complete fuzzing or performance assessment.

## Payload and source/license correspondence

`tools/compression/profile.json` declares exact source/notice exports and digests, the upstream compiled source list, original-source ZIP identity and native probe contract. `lib/` contains the static archive; `include/` contains the original public header and upstream CMake-configured `zconf.h`. The configured header has an explicit notice identifying its platform configuration. `sources.zip` preserves every selected original file unchanged. `notices/zlib/` retains the full original license, README and public header. `build-report.json` binds SDK/source identities, output hashes, configuration and actual probe results; the dependency artifact manifest additionally identifies all build inputs, flags and payload hashes.

The selected library uses the original Zlib license. Preserve the full notice, identify the original authors accurately, and plainly identify altered source/configuration outputs. No source file in the submodule is modified. Static compilation does not relicense zlib under the first-party Apache license. This component's result does not clear CPython, TLS/CA data, VLC or complete signed application distributions. [Dependency policy](architecture/dependencies.md) and [Syncplay architecture](architecture/syncplay.md) describe the remaining runtime/integration boundaries.
