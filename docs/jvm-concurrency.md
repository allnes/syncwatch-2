# Source-built JVM concurrency

The `kotlinx-concurrency` component builds Atomicfu 0.32.1 and Kotlin coroutines 1.11.0 from pinned Git submodules. It supports the Linux Compose dependency build; it does not provide the Compose UI, a desktop window, native rendering or application acceptance.

The [source profile](../tools/jvm/concurrency.json) inventories every selected original source, notice and build input. The graph includes the existing source-built Kotlin standard library and JetBrains annotations, Atomicfu, coroutines, Android's original `SuppressLint` declaration and Animal Sniffer's original `IgnoreJRERequirement` declaration. All application libraries are Git submodules under `3rdparty`. Android and Animal Sniffer supply compile-time annotations only; their classes do not enter the consumer runtime classpath. The Android selection is one annotation declaration, not an Android framework/runtime dependency.

Atomicfu and coroutines retain their original common, concurrent and JVM source-set refinements. Intermediate `expect` and `actual` declarations are not flattened into one common source set. The original Kotlin/Java files are unchanged. Compilation uses the separately verified Kotlin 2.3.20 developer SDK, explicit language/API version 2.2 and the owned standard library. Compiler SDK runtime JARs remain excluded from target compilation and execution.

This is an explicit untransformed JVM profile. Atomic operations use Atomicfu's original JVM runtime; no Gradle, Atomicfu bytecode transformer, IR transformer, registry-library download or source generator runs. The original Java 9 module descriptors are compiled into multi-release JARs. The coroutines debug-agent replacement resource is compiled from its original integration-test source. The upstream precompiled `DebugProbesKt.bin` is excluded from the build inputs.

The binaries retain the original Apache-2.0 notices and source headers. The separate compile-time annotation artifact retains Android's Apache notices and Animal Sniffer's MIT grant and original file copyright. The source archive includes every selected original file, full notices and the exact build profile. This owned profile is not a claim of equivalence with the upstream Gradle artifacts.

From the repository root:

```sh
python3 tools/dependencies/build.py prepare --component kotlinx-concurrency --platform linux-x64
python3 tools/jvm/jdk.py --provision
python3 tools/jvm/kotlin.py --provision
python3 tools/dependencies/build.py build --component kotlinx-concurrency --platform linux-x64 --cold
python3 tools/dependencies/build.py build --component kotlinx-concurrency --platform linux-x64
```

Use `macos-arm64` or `windows-x64` on the corresponding developer host. Preparation and explicit SDK provisioning may access the network. The registered build and restored-cache verification use the selected local sources offline.

Verification checks the owned Kotlin runtime, exact per-target binary hashes, complete original-source correspondence, notices and module descriptors. Consumers exercise runtime code origins, atomics, concurrent scheduling, mutex ownership, bounded channels, state flow, cancellation, failure isolation and future interoperation. They execute with an ordinary classpath, the rebuilt debug agent and the original JPMS modules. The debug-agent launch uses a verified temporary copy outside the Unicode consumer working directory and an absolute launch path; runtime classpaths still identify the original payload. This avoids the Windows developer SDK's instrumentation loader expanding a relative agent name against a Unicode directory. Temporary consumer output paths include non-ASCII characters. `jdeps` must resolve only the declared owned modules and `java.base`, `java.instrument` and `jdk.unsupported` SDK modules. This developer execution does not qualify a packaged JVM.
