# Syncplay engine source package

The `syncplay-engine-sources` component produces a reproducible, non-executable source artifact from the pinned `3rdparty/syncplay` submodule. It supports the macOS arm64, Windows x64 and Linux x64 dependency jobs. It does not provide an embedded Python runtime or an initialized Syncplay engine; `syncplay-runtime` remains unavailable.

## Build and verification

Use the declared Python developer SDK (3.12 or newer), Git and the existing dependency infrastructure. No package index or installed third-party Python modules are needed. On macOS:

```sh
python3 tools/dependencies/build.py build --component syncplay-engine-sources --platform macos-arm64 --cold
python3 tools/dependencies/build.py build --component syncplay-engine-sources --platform macos-arm64
python3 tools/syncplay/engine_sources.py verify --platform macos-arm64
python3 -m unittest discover -s tools/syncplay/tests -v
```

Select `windows-x64` or `linux-x64` on the corresponding host. The first invocation rebuilds the source artifact; a matching second invocation restores and revalidates the cache. A platform label is not permission to run on a different operating system.

`tools/syncplay/profile.json` declares the exact unchanged source and notice files, original Git revision, source archive identity, standard-library classification and reviewed analysis digest. The package contains the client, protocols, constants, utilities, message dictionaries and player base/initializer references, together with upstream build/requirements metadata. It excludes the external-player implementations, UI implementations, media, browser, fonts and all third-party runtimes.

The output includes:

- `syncplay-engine-sources.zip`: exact original bytes with stable entry order, timestamps and permissions;
- `source-analysis.json`: lexical import sites, selected class method signatures, literal configuration subscripts and unresolved dependencies;
- `source-manifest.json`: exact source/notice identities and explicit `runtimeReady: false`;
- `notices/syncplay/`: the complete original Apache license and README, including its own MIT notice, plus the complete upstream third-party notices.

Cold and restored output must match the complete expected inventory and every original source/notice byte. Isolated child-process probes import the actual upstream constants, messages and utilities, exercise English/Russian messages and version comparison, and reject third-party import, process or network attempts. These probes do not import the client or player package and do not initialize the engine.

## Runtime boundaries

Static imports are candidates, including imports inside methods or conditional branches. Their presence does not prove execution; their absence does not prove dynamic behavior is safe. Configuration subscripts are an inventory of literal indexing expressions, not a complete validated configuration or a set of defaults. Build-reference dependencies such as setuptools are reported separately from engine-source import candidates.

The upstream player initializer eagerly imports external-player implementations. Client methods refer to the unshipped configuration UI; message initialization contains a frozen-macOS PySide locale path. Update/server-list methods include a requests fallback. Those boundaries need explicit headless integration decisions and tests before client initialization.

The upstream protocol can proceed to Hello when TLS is unavailable or refused. Product synchronization requires authenticated TLS without silent downgrade, including reconnect paths. The source package preserves upstream behavior unchanged and enables no connection. Runtime readiness requires a complete pinned CPython/Twisted/TLS/platform source and license graph, headless package/configuration, enforced transport policy, real initialization, lifecycle and server compatibility tests. [Syncplay architecture](architecture/syncplay.md) defines the integration contract.

## License scope

Selected original code is covered by upstream's repository-wide Apache-2.0 declaration. The README carries a separate complete MIT notice; both and the complete upstream third-party notice file are retained unchanged. Retaining notices for unshipped dependencies does not adopt those dependencies. No source modifications or new library versions are introduced by packaging. This selected source-only result does not clear future runtime, TLS/CA data, external-player, GUI or complete application distributions. Each added source set requires its own exact source/notice and distribution review.
