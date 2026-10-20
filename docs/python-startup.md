# CPython startup source profile

The shared startup prerequisite declares an isolated embedding policy for the planned Syncplay helper and checks the required CPython API against pinned original declarations. It packages source references and runs a separate developer-SDK isolation probe on macOS arm64, Windows x64 and Linux x64. It does not build or ship an interpreter. The syncplay-runtime component remains unavailable.

## Source and policy

The 3rdparty/cpython submodule is pinned to CPython 3.12.15 at e848e4b09ca4bc67c0041c9ce7526dae471d4c36. The selected export contains six unchanged files: the complete LICENSE and README, version header, initialization declarations, and public/non-limited lifecycle declarations. Includes and references in these files do not enable interpreter implementations, standard-library modules or native extensions. The selected headers alone are not a complete compilable embedding SDK.

The [profile](../tools/python-runtime/profile.json) owns the exact source/notice digests, required function signatures and field types, proposed PyPreConfig/PyConfig overrides and explicit package-owned path fields. The policy ignores environment and argument parsing, disables site/user-site imports, bytecode and signal-handler installation, selects UTF-8, and requires explicit module-search paths. A future native implementation must supply verified absolute package paths, initialize through the matching isolated configuration API, handle status/cleanup correctly, and verify actual path resolution and lifecycle. The declaration inspector strips comments and checks the selected pinned declarations; it does not preprocess C or establish platform layouts, linkage or ABI.

## Developer-SDK checks

Use an installed CPython 3.12 or newer as a developer tool. Its version and executable digest are included in cache inputs; it is separate from the pinned source version and is never copied into the payload.

The probe starts that absolute executable with -I -S -B -X utf8. An owned Unicode temporary workspace supplies controlled invalid PYTHONHOME, injected PYTHONPATH/user-base/startup settings and shadow modules. The child checks actual isolation flags, exclusion of its working directory and injected paths, absent implicit customization, unavailable poison module, no bytecode and a UTF-8 filename/content round trip. It inherits only required Windows OS-root variables, owns its synthetic files, has a 30-second deadline and accepts at most 4096 diagnostic bytes. Diagnostic output contains case results rather than private environment values or search paths.

These checks exercise only the developer SDK's CLI behavior. They do not prove the proposed embedding overrides, configured headers, pinned interpreter, native ABI or package path behavior. The nativeRuntimeBuilt, embeddingAbiVerified and runtimeReady fields remain false.

## Build and verify

Run on the corresponding native host:

~~~sh
python3 tools/dependencies/build.py prepare --component cpython-startup-sources --platform macos-arm64
python3 -m unittest discover -s tools/python-runtime/tests -v
python3 tools/dependencies/build.py build --component cpython-startup-sources --platform macos-arm64 --cold
python3 tools/dependencies/build.py build --component cpython-startup-sources --platform macos-arm64
~~~

Use linux-x64 on Linux or python and windows-x64 on Windows. Both a build and restored-cache verification recheck the original source inventory, declaration analysis and complete payload, then run a fresh SDK isolation probe. Unknown files, altered sources/notices, missing selection summary, changed declarations or failed probes reject the artifact.

The payload contains the deterministic unchanged sources.zip, declaration analysis and source manifest, SDK case results, original full LICENSE/README notices and SELECTION.txt. The latter identifies the source-reference selection and separate first-party additions. The selected Python-2.0.1 license chain retains PSF, BeOpen, CNRI 1.6.1 and CWI terms; the complete upstream text also retains the documentation-code license alternative. No original source file is modified or relicensed under Apache-2.0.

Full interpreter/core/standard-library and platform-extension source graphs, embedded origins, generated sources, packaged runtime libraries, TLS/CA data and Twisted/transitives need separate source/license and binary correspondence closure. Native embedding/ABI, authenticated TLS, real engine initialization, helper IPC, lifecycle and interoperability remain separate gates in the [Syncplay architecture](architecture/syncplay.md).
