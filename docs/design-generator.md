# Building the design tools

The native design-tool profile runs Style Dictionary 5.7.0 from pinned source. It uses Node.js 24.3 or newer within the 24.x release line, Python 3.12 or newer, and Git. Node and Python are developer toolchains; neither is required by the native application to display generated resources.

Run from the repository root, with the selected Node executable on `PATH`:

```sh
python3 tools/design/check.py --cold
```

On Windows use `python tools/design/check.py --cold`. The command detects macOS arm64, Linux x64, or Windows x64, initializes the exact Git links, exports clean source snapshots, builds the tool, and exercises its API with registry access disabled. Source initialization needs access to the declared Git remotes on first use. Omit `--cold` to allow a previously verified artifact with identical inputs and toolchains.

The output is `artifacts/dependencies/design-generator/<platform>/payload/runtime/`. It contains a local `node_modules` tree, `runtime.mjs`, `source-map.json`, resolved `design-values.json`, `license-inventory.json`, and `THIRD-PARTY-NOTICES.txt`. Each package retains its full license/notices and original package metadata. The runtime also contains the first-party Apache license, so it can be distributed with its notices as a standalone tool. The enclosing dependency artifact's `build-manifest.json` identifies source revisions, toolchains, build inputs, and payload hashes. Generated artifacts and caches are ignored by Git.

## Source profile

[sources.json](../tools/design/sources.json) specifies the 15 source modules, package entry points, selected files, dependency edges, native import bindings, and exclusions. The [component registry](../tools/dependencies/components.json) pins their Git revisions, upstream notice paths, target toolchains, and build recipe. No npm install, lifecycle script, registry package, upstream bundle, Rollup, or TypeScript package is used.

The build copies JavaScript source directly. For TypeScript libraries, Node's built-in `stripTypeScriptTypes` compiler emits JavaScript. Glob's implicit type-only imports receive explicit type modifiers before compilation, preserving the import elision normally performed by its upstream TypeScript build. Style Dictionary receives its source package version and a Node filesystem binding in place of its eager browser filesystem import. Original submodule worktrees stay unchanged. `source-map.json` records each emitted file's original source path, source digest, output digest, and transformation.

The profile binds Style Dictionary directly to the original Deepmerge and Glob Node sources and the standard Node `path` API. It does not redistribute browser wrappers or an adapted copy of Node's path implementation. Deepmerge requires the explicit mergeability predicate that Style Dictionary already supplies; its unused eager fallback dependency is removed from the selected build. Native import bindings and fallback removal are recorded as source transformations. Modified JavaScript carries a prominent SyncWatch notice, and modified package metadata has a `syncwatchModifications` field.

[licenses.json](../tools/design/licenses.json) records the reviewed license text digests and embedded-source attribution. Chalk retains its upstream ANSI/color-detection sources under the same MIT copyright/permission text. Color.js retains its inline HSLuv/HPLuv MIT notices, and the original MIT notice for the HCT implementation is included separately. The source recipe rejects changed or incomplete notice texts and checks prominent modification notices. The same license checker runs after cache restoration. See [licenses and distribution](licenses.md).

The supported API uses Node's filesystem, JSON/JSON5 token input, upstream transforms, reference resolution, JSON flat/nested output, and explicitly supplied `syncwatch/` formatters. The `style-dictionary/utils` entry exposes upstream reference and formatting helpers through a native-profile barrel. Browser Memfs, ZIP download/conversion utilities, the upstream CLI, and Prettier-backed JavaScript/TypeScript formats are outside this profile. They are excluded explicitly rather than resolved from an ambient package installation. Native Swift and WPF formatters use the custom formatter API.

## API

Import `createDictionary` from the built `runtime.mjs`, supply an explicit configuration object, then use the returned upstream dictionary:

```js
const dictionary = await createDictionary({
    source: ['packages/design/tokens/*.json'],
    log: {verbosity: 'silent', warnings: 'error'},
    platforms: {
        json: {
            transforms: ['name/camel'],
            files: [{destination: 'tokens.json', format: 'json/flat'}],
        },
    },
});
const results = await dictionary.formatAllPlatforms();
```

For native formats, provide functions in `hooks.formats` under the `syncwatch/` namespace and select those names in the platform's files. The source profile rejects unsupported formats before creating the dictionary. Its process-wide import guard rejects modules outside the built source tree and undeclared Node builtins, and disables Fetch/WebSocket access. Run it in a dedicated build process. This guard provides reproducible module resolution; it is not an OS sandbox for untrusted configuration code.

The source recipe runs API checks in fresh processes, including shared token values, JSON5/glob input, aliases, legacy/DTCG colors, custom formatting, broken/cyclic references, unsupported formats, blocked network/ambient imports, and emitted-file correspondence. The generated native resources and UI components are described in the [design architecture](architecture/design-system.md).

## Native resource generation

The native formatters resolve `packages/design/tokens/*.json` with Style Dictionary and generate the five checked-in files under `packages/design/generated/`. The Swift package at `packages/design/Package.swift` exposes `SyncWatchDesign`. Both the WPF application and its SDK-only design assertion executable compile the linked generated C# and XAML directly.

```sh
python3 tools/design/resources.py
python3 tools/design/resources.py --check
node --test tools/design/tests/resources.test.mjs
```

The first command builds or verifies the source-only tool and writes resources. The second compares all five outputs without changing them. Use `--cold` to rebuild the tool without reading its dependency cache. CI runs the comparison and resource tests in each of the three design dependency jobs, including after a cache restore. Native jobs compile the committed resources and test real SwiftUI/AppKit and WPF values.

Token files are flat JSON files with distinct root groups. Each leaf has `type` and `value`. Supported types are `color` and `number`. Colors use sRGB `#RRGGBB` or `#RRGGBBAA`; output alpha is preserved, including WPF's different `#AARRGGBB` order. Numbers are finite logical dimensions in `[0, 1000000]`, rounded to six decimal places using `Math.round(value * 1000000) / 1000000`. Physical-unit strings are rejected. A complete `{token.path}` alias must refer to the same type; Style Dictionary resolves chains and rejects cycles. Native identifiers use the path segments joined in camel/Pascal case. Invalid segments, reserved names, and collisions are errors.

`themes.json` maps the same semantic color roles in dark and light themes to token IDs. Shared roles reference the same accent/status colors. SwiftUI resolves a `SyncWatchTheme` from the environment's color scheme. WPF loads `SyncWatchTheme.g.xaml` and merges `theme.dark` or `theme.light`; controls bind `theme.<role>.brush` with `DynamicResource`. The current shell follows the Windows application appearance preference and refreshes on preference changes. The complete theme/settings interface remains separate component work.

Swift exposes typed constants and ID-indexed `colors`/`dimensions` dictionaries. C# exposes typed `Color` properties and `double` constants, with uniform `Thickness`/`CornerRadius` projections for dimensions. XAML uses the original token ID as each `Color`/`Double` resource key and adds `.brush`, `.thickness`, and `.cornerRadius` projections. These projections preserve values; callers choose the appropriate geometric meaning.

`design-manifest.json` records schema version 1, units, sorted resolved token IDs/values, theme mappings, per-source SHA-256 digests, a combined source digest, and a generator revision. The generator revision hashes its implementation files and pinned upstream revisions. It is independent of the checkout path, unrelated Git commits, and build time. Tokens/copy/components/package/theme changes update the design source digest. Do not edit generated files manually.
