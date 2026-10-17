# Building the design tools

The native design-tool profile runs Style Dictionary 5.7.0 from pinned source. It uses Node.js 24.3 or newer within the 24.x release line, Python 3.12 or newer, and Git. Node and Python are developer toolchains; neither is required by the native application to display generated resources.

Run from the repository root, with the selected Node executable on `PATH`:

```sh
python3 tools/design/check.py --cold
```

On Windows use `python tools/design/check.py --cold`. The command detects macOS arm64, Linux x64, or Windows x64, initializes the exact Git links, exports clean source snapshots, builds the tool, and exercises its API with registry access disabled. Source initialization needs access to the declared Git remotes on first use. Omit `--cold` to allow a previously verified artifact with identical inputs and toolchains.

The output is `artifacts/dependencies/design-generator/<platform>/payload/runtime/`. It contains a local `node_modules` tree, `runtime.mjs`, `source-map.json`, and resolved `design-values.json`. The enclosing payload also contains upstream notices. The dependency artifact's `build-manifest.json` identifies source revisions, toolchains, build inputs, and payload hashes. Generated artifacts and caches are ignored by Git.

## Source profile

[sources.json](../tools/design/sources.json) specifies the 19 source modules, package entry points, selected files, dependency edges, and exclusions. The [component registry](../tools/dependencies/components.json) pins their Git revisions, upstream notice paths, target toolchains, and build recipe. No npm install, lifecycle script, registry package, upstream bundle, Rollup, or TypeScript package is used.

The build copies JavaScript source directly. For TypeScript libraries, Node's built-in `stripTypeScriptTypes` compiler emits JavaScript. Glob's implicit type-only imports receive explicit type modifiers before compilation, preserving the import elision normally performed by its upstream TypeScript build. Style Dictionary receives its source package version and a Node filesystem binding in place of its eager browser filesystem import. Original submodule worktrees stay unchanged. `source-map.json` records each emitted file's original source path, source digest, output digest, and transformation.

The profile uses the upstream unbundled Deepmerge wrapper and Glob's Node entry. Chalk's vendored ANSI/color detection sources and Path-unified's adapted Node path sources remain in their upstream pinned modules. Three upstream wrappers and the mergeability helper supply license declarations in package manifests rather than standalone license files; those manifests and their READMEs are retained alongside the other upstream licenses/notices.

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
