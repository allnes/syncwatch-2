# Building the JVM annotations dependency

The `jvm-annotations` component builds JetBrains Java Annotations 26.0.2 from the pinned `3rdparty/jvm-annotations` source using the JDK compiler directly. It does not use Gradle, Maven packages, Kotlin compilation or annotation processors. This component is one dependency of the planned Kotlin/Compose client; the full UI/native/build/runtime source graph remains unresolved.

## Source and licensing

The [reviewed profile](../tools/jvm/annotations.json) identifies all 32 unchanged Java source files, their SHA-256 digests, source revision, notices and expected JAR digests. The JVM API has no external library dependency. Its module descriptor retains the upstream static requirement on the SDK module `java.desktop`.

The source uses Apache-2.0. Thirty files retain their original Apache copyright/license headers. `CheckReturnValue.java` and `NotNullByDefault.java` have no individual header; their licensing basis is the repository-wide Apache declaration in the retained README and publishing configuration. No copyright statement is synthesized for them. This revision has no upstream `NOTICE` file.

Common/non-JVM Kotlin sources, multiplatform metadata, upstream Gradle/publishing/signing tools and non-JVM targets are excluded. They are not required by this Java classpath/named-module profile. The resulting artifacts have a SyncWatch profile name and are not upstream signed Maven binaries.

## Developer compiler SDK

[The toolchain manifest](../tools/jvm/toolchains.json) pins Eclipse Temurin JDK 21.0.12.1+1 for Linux x64, macOS arm64 and Windows x64. It records official vendor archive SHA-256 values and complete installed file/symlink inventory digests. Provisioning and reuse verify the complete inventory, vendor legal files and exact compiler version. No system Java installation or default is changed.

This JDK is a developer SDK under the [toolchain exception](architecture/dependencies.md#complete-source-graph). Its vendor legal directory retains GPLv2, the Classpath Exception on designated files and separately licensed components. The SDK is not copied into library artifacts or an application package. A future bundled JVM needs its own source/license and distribution review.

## Commands

Run from the repository root, using `python` where required on Windows:

```sh
git submodule update --init --checkout --depth=1 -- 3rdparty/jvm-annotations
python3 tools/jvm/jdk.py --provision
python3 tools/dependencies/build.py build --component jvm-annotations --platform linux-x64 --cold
python3 tools/dependencies/build.py build --component jvm-annotations --platform linux-x64
python3 -m unittest discover -s tools/jvm/tests -v
```

Use `macos-arm64` or `windows-x64` for those platforms. The SDK is installed in the checkout's ignored `.local/toolchains` directory. An official local archive can be supplied with `--provision --archive PATH`; all pinned checks still apply. Provisioning is the explicit online SDK step. Library compilation and verification use the dependency builder's offline environment.

The profile compiles 31 API files with Java release 8, UTF-8, no debug information, no processors and isolated class/source paths. The unchanged module descriptor is compiled separately for release 9. Sorted entries, fixed timestamps and stored ZIP bytes produce deterministic multi-release JARs. The source and compiler configuration must reproduce the reviewed output digests.

Every cold build and restored cache runs its `verifyCommand` before success, artifact packaging and trusted-cache publication. This validates the complete payload, notices inside both JARs, original source JAR bytes and source/compiler correspondence. A failed verifier clears the payload and retains only the failure manifest. Required dependency CI runs the profile on all three supported build platforms.

Verification compiles a real Java 8 type-use/contract consumer, runs 14 reflection/module assertions, requires invalid annotation-target compilation to fail, and checks the SDK-only compiled dependency graph with `jdeps`.

## Outputs

The payload under `artifacts/dependencies/jvm-annotations/PLATFORM/payload` contains the binary and original-source JARs, `THIRD-PARTY-NOTICES.txt`, `source-inventory.json`, and the unmodified upstream license/README under `notices/jvm-annotations`. Both JARs include the complete license, notices, README and source inventory. Preserve these texts and provenance when distributing this profile. No upstream Java source is modified. Source, module, compiler or packaging changes require a new review and reproducible output digests.
