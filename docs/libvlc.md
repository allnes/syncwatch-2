# Native libVLC SDK

The `libvlc` component builds VLC 3.0.24 and its selected codec, audio, text and font dependencies from the exact Git submodules registered in `3rdparty/`. It targets native macOS arm64, Windows x64 and Linux x64. This is a decoder SDK; the application playback adapters and native video/audio surfaces are separate integrations.

## Build and revalidate

Provision developer tools before preparing the offline source graph:

```sh
python3 tools/vlc/provision_sdks.py
python3 tools/dependencies/build.py prepare --component libvlc --platform macos-arm64
python3 tools/dependencies/build.py build --component libvlc --platform macos-arm64 --cold
python3 tools/vlc/runtime.py verify --platform macos-arm64
```

Use `linux-x64` on Linux. On Windows use `python` and `windows-x64`. CI provisions its developer SDK before running the same prepare/build/verify entry points. Preparation exports exact original Git blobs, including complete selected notices, rather than filtered checkout bytes. The recipe disables automatic downloads, Meson wraps, FFmpeg autodetection and network support. A restored dependency cache must pass the complete source, grant, payload, native-import, codec-configuration and fresh-consumer checks again.

macOS uses the selected Apple SDK plus GNU M4, Autoconf, Automake, Libtool, Gettext, Bison, Flex, Gperf, pkgconf, CMake and Ninja. Linux also needs NASM, GNU config helpers and patchelf. Developer provisioning is an explicit online step; the application libraries are built offline from their source pins. Windows uses a separate MSYS2 UCRT developer SDK with the base archive and every installed package fixed by digest in `tools/vlc/windows-sdk.json`; provisioning leaves the bootstrap SDK intact. An explicitly selected existing Windows developer SDK can be provided through `SYNCWATCH_VLC_MSYS_ROOT`. Compiler support notices remain separate from application-library grants. No SDK zlib, iconv or winpthread binary becomes an application dependency.

## Selected sources and media behavior

`tools/vlc/profile.json` records the exact files, original executable inventory, notices, source edges and plugin selection. The graph contains VLC, FFmpeg, dav1d, source-built zlib, FreeType, HarfBuzz, FriBidi, libass, libsamplerate, Fontconfig, Expat, GNU libiconv, Meson, the separately pinned Unicode authority and source-built winpthreads for Windows. Fontconfig/Expat serve Linux; GNU iconv serves Windows; CoreText and DirectWrite are platform font providers. Font files come from the OS or user and are not bundled by this component.

Linux retains Fontconfig's original default alias, matching, hinting and fallback rules from its pinned source. The configuration is relocated into the owned package and checked against those source bytes on every verification. The consumer selects that configuration directory explicitly; it does not rely on a configuration left in the build prefix.

FFmpeg uses dynamic libraries with GPL, version3 and nonfree components disabled. The actual libraries must report the expected license, version and configuration through their own APIs. FreeType uses its FreeType License choice. The full original grants and embedded notices are retained, including license alternatives for excluded original sources.

Fresh native consumers check authored I420/PCM, H.264/AAC, 1080p H.264/AAC and 4K HEVC/AAC fixtures. They observe metadata, decoded frames, resampled PCM and its known tone, pause stability, forward and backward seek pixels, stop, reload and release. Separate effect cases check actual brightness changes, normalization amplitude, pitch preservation during time stretching, replacement by an external audio tone and rendered SRT/ASS subtitle pixels. These are memory-callback observations; they establish no physical display, speaker, GPU-surface or application acceptance.

On Windows, the consumer loads the verified owned shared-library closure before initializing VLC. Its dependency search permits only the owned DLL directory and System32, and it rejects a loaded library with a foreign path. Handles remain owned until all players and the VLC instance are released. This is required because VLC's plugin loader restricts dependency discovery to System32; a developer SDK or working-directory search must not provide missing application libraries.

VideoToolbox/CVPX modules are selected on macOS, and D3D11VA on Windows. Hardware availability and playback controls need separate qualification. H.264 VideoToolbox backward seeking is unqualified; software decoding remains the accepted consumer path. Linux currently has a headless software decoder profile. Native Linux surfaces and the full Compose runtime remain separate prerequisites.

## Corresponding sources and declared changes

The payload contains headers, owned dynamic libraries, selected plugins, full notices, per-source original ZIPs, exact configured VLC files, first-party rebuild recipes, source inventories, compiler SDK identity, command flags, import closure and a payload digest report. ZIP entries preserve original bytes; executable modes are reconstructed from the retained profile inventory. The SDK and its build executables are not distributed as application libraries. Dynamic dependencies must remain replaceable when packaging an application.

Four VLC files have explicit derivatives. `src/revision.txt` records the base source pin. `configure.ac` uses that original commit's date instead of the current clock. `lib/media_player.c` inherits an explicitly configured audio-filter list when creating a player: the original empty variable otherwise masks the initialization setting, leaving normalization inactive. `modules/common.am` links Windows plugins to the owned shared codec libraries while retaining static compiler support, replacing the upstream assumption that every contrib library is static. The changed files retain their original grants and a dated change notice. The exact configured files accompany the original sources; this is a modified build of the recorded base revision.

The GNU iconv mirror's pinned MSVC patch is reversed only in an isolated source tree. Every restored file must match the complete original GNU release inventory. The libraries and public headers are built; the GPL command-line program is not packaged. macOS selects VLC's original pipe/dup fallbacks for its deployment floor. VLC uses C11 explicitly, and its Windows configure step sees the Windows 10 API baseline so that its synchronization import-library check matches the compiler headers.
