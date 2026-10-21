# Native hash library

The `hacl-hash` component builds a static C library from the four original HACL* hash sources selected by pinned CPython. It supports macOS arm64, Windows x64 and Linux x64. This dependency is a prerequisite for an embedded interpreter; the component does not build CPython or enable synchronization.

## Build and verification

Use Python 3.12 or newer, CMake 3.30 or newer, and the native C SDK: Apple Clang and the macOS SDK, Visual Studio 2022 C build tools and Windows SDK, or GCC/Clang and platform development headers. SDKs and native symbol inspectors are developer tools and are not packaged. No package registry, proof generator or implicit library download is used.

```sh
python3 tools/dependencies/build.py build --component hacl-hash --platform macos-arm64 --cold
python3 tools/dependencies/build.py build --component hacl-hash --platform macos-arm64
python3 -m unittest discover -s tools/hashing/tests -v
```

Use `windows-x64` and `python` on Windows, or `linux-x64` on Linux. The second build exercises cache restoration. The tests need the selected source snapshots; `build.py prepare --component hacl-hash --platform <target>` also creates them without compiling.

Cold builds compile the selected original sources twice and require byte-identical static archives. Every verification, including cache reuse, freshly compiles the pinned sources, compares the entire payload and exact archive bytes, inspects defined native symbols, then links and executes an independent probe against the accepted archive. Apple archive timestamps are controlled with `ZERO_AR_DATE=1`; compiler path mapping and MSVC deterministic archive options remove temporary build paths. Outputs are never rewritten to make comparisons pass. Reproducibility is checked within the recorded native SDK identity, not across different compilers or operating systems.

The probe checks MD5, SHA-1, SHA-224/256/384/512, SHA3-224/256/384/512 and SHAKE128/256. Frozen empty, `abc`, padding, block and rate-boundary inputs cover 19 vectors through 1,025 bytes, including 192-byte SHAKE output. It verifies 228 one-shot known answers and 1,140 streaming cases with five chunk sizes, repeated digest, zero-length update, independent state copy/reset, appending `Z` after digest, and output boundaries. Frozen answers are also compared with the independent developer Python hash API. This establishes these API cases; it does not establish a new formal proof, side-channel assessment or cryptographic certification. MD5 and SHA-1 are compatibility algorithms and must not be used for authentication or security-sensitive integrity decisions.

## Source and namespace ownership

[The profile](../tools/hashing/profile.json) and [component registry](../tools/dependencies/components.json) define all 48 original files and complete notices at exact Git submodule revisions:

| Source | Selected responsibility | License |
|---|---|---|
| CPython | Original refresh/reference files binding the four C sources to the HACL revision | Python-2.0.1, including the full historical license chain |
| HACL* | Four original generated hash C files, original public/internal headers, generator provenance and original runtime-header copies | MIT for generated sources; full upstream Apache-2.0 and MIT texts retained |
| KaRaMeL | Exact original runtime-header closure, byte-matched with the HACL vendor copies and generator revision | Apache-2.0 |
| Arduino Crypto | Original cited endian-macro source and full Southern Storm Software MIT notice | MIT |

The original vendor files remain unchanged. A separate first-party generated preinclude maps HACL identifiers to `python_hashlib_Hacl_*`, and a wrapper selects the verified portable uint128 implementation. Native symbol inspection rejects missing required hash functions and unprefixed HACL exports. Eleven KaRaMeL headers must match their original HACL copies byte for byte. The endian source attribution and canonical 32/64-bit macro bodies are checked against the separately pinned Arduino source. Generator/proof-tool revisions are provenance references; those tools are neither built nor adopted by this profile.

## Distribution

The payload contains a static `.a` or `.lib`, original public/internal/runtime headers, a separate namespace header and wrapper, an original-source ZIP, selection notes, complete original notices and a build report. The report binds the source inventory, compiler/SDK/symbol-tool identity, defined symbols, fixture result, build configuration and every other payload file digest. No executable, interpreter, SDK runtime, shared library or TLS provider is distributed.

Preserve the full notices and original attributions, source inventory and source/binary correspondence when distributing this component. Any future modifications to upstream files require appropriate prominent change notices. The first-party build wrapper remains Apache-2.0. See [licenses and distribution](licenses.md).

The complete CPython core, standard-library/platform source graph, embedding ABI, package-path validation, TLS/CA dependencies, Twisted and Syncplay remain unresolved. The Linux application also requires its separate Compose/compiler/native/font source and license closure before it can be built or distributed.
