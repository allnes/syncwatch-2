# Building JBR API

The `jbr-api` component builds JetBrains Runtime API 1.9.0 from the pinned `3rdparty/jbr-api` source. This optional-service interface library is a dependency in the planned Compose desktop graph. The component uses the same [verified developer JDK](jvm-annotations.md#developer-compiler-sdk) as JVM annotations, without Gradle, Maven, downloaded library binaries or a JBR runtime.

## Selected source and license scope

[The profile](../tools/jvm/jbr_api.json) records the exact revision and SHA-256 inventory of 28 API Java files, seven build-tool Java files, the JBR Java template, service-getter template, API compatibility baseline and provenance files. All 36 Java files have original Apache-2.0 headers. The profile has no external library dependencies; runtime references use `java.base` and `java.desktop`, and the build tools use `jdk.compiler`. No upstream `NOTICE` exists at this pin.

The API files are unchanged. A [reviewed build-source patch](../tools/jvm/patches/jbr-api-ordering.json) sorts generated services, extensions and proxy metadata in `SourceGenerator.java`. The modified file and generated `JBR.java` carry prominent change notices. Both original and modified build sources, the exact patch, original headers, full license and generated `JBR.java` are retained in the source JAR. The binary and source JARs also contain full notices, the upstream README and source/compiler inventory.

JBR/OpenJDK runtime implementations, native code, fonts, javadoc generation/assets, publishing tools and upstream manual GUI tests are outside this profile. The API's presence does not select or bundle JetBrains Runtime. On ordinary Temurin, JBR services are unavailable except the upstream font-metrics fallback. Packaged JVMs and the full Compose/native/font graph require their own source, license and distribution review.

## Build and verification

Run from the repository root on Linux:

```sh
git submodule update --init --checkout --depth=1 -- 3rdparty/jbr-api
python3 tools/jvm/jdk.py --provision
python3 tools/dependencies/build.py build --component jbr-api --platform linux-x64 --cold
python3 tools/dependencies/build.py build --component jbr-api --platform linux-x64
python3 -m unittest discover -s tools/jvm/tests -v
```

This component belongs to the Kotlin/Linux application and is built and probed only on Linux. macOS/Swift and Windows/C# do not provision a developer JVM for it. SDK provisioning is an explicit online step. Compilation and artifact verification use the dependency builder's offline environment, isolated class/source/processor paths, UTF-8 and no debug information. `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, `JDK_JAVAC_OPTIONS`, `_JAVA_OPTIONS` and ambient classpaths are removed from compiler and probe environments.

The source-built upstream annotation processor generates `JBR.java` and compares the API against the pinned upstream 1.9.0 compatibility baseline. The reviewed ordering patch changes only the generated source hash: the processor reports a patch-level `1.9.1` source change with an empty structural API diff. The build requires that exact result, while the module retains API version `1.9.0` and artifacts use a distinct SyncWatch profile name. Java 9 compilation retains module version `1.9.0`. The source-built upstream compatibility plugin compiles the Java 8 surface and removes duplicate Java 9 classes. Sorted entries, stored ZIP bytes and fixed timestamps/modes produce reviewed, deterministic multi-release JARs. Compiler tools are excluded from the binary JAR.

Cold and restored-cache builds both verify the complete payload, fixed JAR digests, licenses, unchanged and modified sources, modification notices and generated-source digest before success or publication. A real Java 8 consumer compiles service, callback and extension APIs. Runtime assertions exercise classpath, named-module and Java 8 overlay loading, optional service predicates/getters, extensions and the font fallback on ordinary Temurin; `jdeps` checks SDK-only dependencies. Disabling multi-release loading tests the Java 8 bytecode branch on the pinned JDK; it is not execution on a Java 8 VM or a real JBR implementation. These headless checks do not validate Compose windows or JBR-specific native services.

## Artifacts

The payload under `artifacts/dependencies/jbr-api/PLATFORM/payload` contains `jbr-api-1.9.0-syncwatch.jar`, its source JAR, `THIRD-PARTY-NOTICES.txt`, `source-inventory.json` and the original license/README under `notices/jbr-api`. Preserve these texts, source correspondence and modification notices when distributing this profile. No SDK/runtime binary is included. Source, compiler, patch or packaging updates require renewed review and output digests.
