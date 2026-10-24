# Kotlin JVM runtime and compiler

The `kotlin-stdlib` component builds the selected Kotlin 2.3.20 standard library and Java Annotations from pinned Git submodules under `3rdparty`. The same recipe runs on macOS ARM64, Windows x64 and Linux x64. It requires no Gradle, Maven, registry libraries or dependency downloads during compilation.

Provision the developer SDKs explicitly, then build on the actual target:

```sh
python3 tools/jvm/jdk.py --provision
python3 tools/jvm/kotlin.py --provision
python3 tools/dependencies/build.py build --component kotlin-stdlib --platform linux-x64 --cold
python3 tools/native/check_kotlin_domain.py
```

Use `macos-arm64` or `windows-x64` on those hosts, and `python` on Windows. Ordinary builds and cache verification never provision SDKs. Optional `--archive` and `--sbom` arguments to the compiler provisioner accept the exact pinned vendor files offline.

## Source and runtime boundary

The [source selection](../tools/jvm/stdlib_sources.json) covers 202 common Kotlin files, 177 platform Kotlin files, 32 Java files and the original Java 9 module descriptor. The existing source package retains additional compile-only declarations and Unicode generator references; those references are not executable build inputs. Original source bytes, published Unicode 13 data correspondence, copyright notices and complete selected Apache, BSD, Boost and Unicode grants accompany the runtime.

The [binary profile](../tools/jvm/stdlib.json) compiles common, JVM, JDK7 and JDK8 declarations together into one Kotlin metadata module. This consolidated profile differs from upstream's multi-stage Gradle build. It uses JVM-default `enable` against Java 8 APIs, retaining legacy `DefaultImpls` compatibility while allowing Java interface defaults; upstream builds its main stage against Java 6 APIs with defaults disabled. Its output is a SyncWatch artifact, with no claim of binary equivalence to the vendor JAR. The only modified source file is `KotlinVersion.kt`: its build copy substitutes the upstream `KotlinVersion(2, 3, 255)` placeholder with `KotlinVersion(2, 3, 20)` and carries an inline modification notice. The package retains the unchanged original, modified copy and explicit change notice. Kotlin and Java classes target Java 8; the original module descriptor targets Java 9 in a multi-release JAR. Kotlin builtins and metadata are emitted by the compiler from source.

Java Annotations is built from its own registered source profile as part of the component. Only these source-built JARs enter consumer compilation and runtime. The compiler runs in a separate process with explicit `-no-stdlib`, `-no-reflect`, JDK and application classpath arguments; including the SDK runtime or using SDK JARs on the target classpath is rejected. Kotlin and javac read UTF-8 tool argument files. The short Java launch carries classpaths through a temporary manifest-only JAR with encoded file URIs, avoiding the Windows native launcher's code-page-dependent argument-file and classpath decoding. It preserves the working directory and exact runtime origins without changing machine locale settings.

## Developer compiler SDK

The [SDK manifest](../tools/jvm/kotlin_toolchain.json) pins the official JetBrains release archive, vendor SPDX document and all 119 original files, including 53 legal files. Provisioning verifies archive sizes and hashes, rejects unsafe ZIP members, and preserves the complete vendor inventory. Every use rechecks installation integrity. The compiler version is checked during toolchain validation.

This compiler is a build-platform SDK exception. Its bundled implementation dependencies, plugins and runtime JARs are not application libraries or distributable runtimes. The declared compiler-process classpath is fixed and optional compiler plugins are disabled by default. The separate [Compose runtime build](compose-runtime.md) explicitly selects its digest-verified Compose compiler plugin by policy name, within the compiler process only. Vendor notices retain their individual licenses: the SDK is not declared wholly Apache-2.0, and its SPDX `NOASSERTION` entries are not treated as license grants. The exception clears no renderer, font or packaged JVM dependency. See [dependency policy](architecture/dependencies.md).

## Acceptance

Cold builds and cache reuse verify exact deterministic JAR hashes per native target, original source/notice correspondence, the named module and its original exports, Kotlin metadata, collection/sequence APIs, Unicode titlecase, regex groups, coroutines, JDK7 paths, Java interface defaults, JDK8 optionals and version reporting. Consumers compile and run in Unicode/space-containing directories and check that Kotlin runtime classes load from the owned JAR. `jdeps` must report only `java.base`.

ARM64 and x64 compiler constant folding emit opposite signs for IEEE NaN in five entries; the remaining output bytes match. Target-specific hashes preserve these original compiler outputs. NaN behavior, public API and source/profile correspondence are checked separately; the difference does not introduce platform-specific application or design versions.

The required dependency lane compiles and executes the Kotlin domain on every target against this runtime. It consumes the same 31 local-state cases and six lifecycle scenarios used by the Swift and C# domains, including generation ownership, atomic persistence, future-format preservation and bounded history. A successful domain check does not qualify Compose galleries, a desktop package, native video or physical output. Those remain separate Linux application requirements.
