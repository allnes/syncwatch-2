# Native renderer object profile

`skiko-native-objects` builds the original GN tool, selected Skia static archives and Linux AWT JNI translation units from ordinary pinned Git submodules. The exact source, header, generator and notice inventories are in `tools/desktop/profile.json`. Common JVM UI sources remain qualified separately on all three development platforms; macOS uses SwiftUI and Windows uses WPF.

The offline recipe stages each source owner at its declared upstream location. Fontconfig receives an isolated public-header directory generated from its original template and pinned cache declarations. D-Bus uses its original architecture template, declared source version and a checked LP64 C ABI. GN's original version template retains the source commit position. Original templates, generated headers, sources and complete selected grants accompany the object package. Cached verification rejects missing or extra artifacts and changed source, generator or notice bytes.

The profile enables text/shaping, SVG, PNG, JPEG, WebP and the selected GPU code. RAW photographic DNG/PIEX decoding is excluded; movie decoding belongs to the independent VLC component. An independent PNG fixture checks a real native Skia decoder and actual pixel values. This is an object/archive and headless decoder check, not desktop or video acceptance.

```sh
python3 tools/dependencies/build.py prepare --component skiko-native-objects --platform linux-x64
python3 tools/dependencies/build.py build --component skiko-native-objects --platform linux-x64 --cold
```

The package contains unlinked JNI objects, static archives and a source-built build tool. It does not supply a qualified linked Skiko runtime or an application. Display clients, font/runtime distribution, the Linux VLC surface and visible application acceptance remain separate requirements. `linux-compose-ui` remains unavailable and `applicationBuildReady` remains false until the full application graph is qualified. Physical synchronization requires all six directed macOS/Windows/Linux sender-observer checks.
