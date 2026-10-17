# Licenses and distribution

SyncWatch's first-party source and shared design data use [Apache License 2.0](../LICENSE). External libraries retain their own licenses; the first-party license does not replace them.

## Design tools

The native Node design profile contains one Apache-2.0 package (Style Dictionary), nine MIT packages, and five BlueOak-1.0.0 packages. These permissive licenses allow use, modification, and distribution with their respective notice conditions. Preserve the full license texts, original copyright/attribution notices, and modification notices when distributing the tool or its source.

Every built runtime includes:

- The first-party Apache license in `LICENSE`.
- A full license and any upstream `NOTICE` inside each package directory.
- Each package's unmodified original metadata in `upstream-package.json`.
- `THIRD-PARTY-NOTICES.txt`, collecting full notice texts and embedded-source attributions.
- `license-inventory.json`, identifying the source revisions, license texts, and modified files.
- Prominent SyncWatch modification notices in changed JavaScript and package metadata.

The [source inventory](../tools/design/sources.json), [reviewed license text digests](../tools/design/licenses.json), and [component registry](../tools/dependencies/components.json) specify the exact distributed profile. Embedded Chalk sources share the retained Sindre Sorhus MIT notice. Color.js's HSLuv/HPLuv copyright and permission headers are retained verbatim; the ColorAide notice identifies the original HCT implementation's author and terms. Supplemental notice provenance is recorded with an upstream reference and digest. No copyright holder or year is synthesized from a username or commit date.

The build verifies license text digests, original license declarations, embedded-source attribution, and modification notices. The distribution check also runs on a restored design-tool cache:

```sh
python3 tools/design/check.py
```

The [build guide](design-generator.md) describes the supported runtime profile. Node and Python are developer toolchains; they are not needed to display generated native resources.

## JVM annotations

The source-built [JVM annotations profile](jvm-annotations.md) uses Apache-2.0 with the full upstream license and original notices in both JARs and the payload. All 32 selected Java sources remain unchanged, including two files governed by the repository-wide declaration without individual headers. The binary JAR links only to Java SDK interfaces; no external runtime library or annotation processor is included. Its Temurin compiler SDK retains vendor legal files separately and is not included in the library or application artifacts.

The source-built [JBR API profile](jbr-api.md) uses Apache-2.0 and retains the full license and original headers for all selected API/build Java sources. A modified source generator sorts metadata; its prominent change notice, original and modified sources and exact patch accompany the artifacts. The binary includes optional-service interfaces and the upstream Java fallback, linked to SDK interfaces only. The source-built processor/plugin are build tools, excluded from the binary JAR. No JBR/OpenJDK runtime, native service implementation or font is packaged. Preserve the source inventory, notices and modification notice when distributing this profile; a future JVM distribution requires separate review.

The dependency verifier checks notices, the original source inventory, and source/compiler correspondence on restored caches as well as cold builds. These checks cover only the declared annotations profile. The Compose/native graph and any packaged JVM runtime require separate source and distribution reviews.

## Other components

The [dependency architecture](architecture/dependencies.md) records the other pinned sources. Syncplay uses Apache-2.0; fastjsonschema uses BSD-3-Clause and retains its license in the built validator package. The native shells and metadata service use the declared platform SDKs/frameworks without registry library packages.

VLC contains code under multiple licenses. The libVLC API is LGPL-2.1-or-later; the complete player, plugins, codecs, and contrib libraries require a distribution inventory for the selected build. Preserve applicable licenses and corresponding source, and support the replacement/relinking rights required by the selected LGPL distribution method. A license entry for the top-level VLC repository is not clearance for every possible module combination. The media component is not yet a registered distributable build.

The planned Linux UI uses Kotlin/JVM and Compose Multiplatform Desktop. JetBrains-owned [Compose code](https://github.com/JetBrains/compose-multiplatform/blob/master/license/README.md), [Kotlin code](https://github.com/JetBrains/kotlin/blob/master/license/README.md), and [Skiko](https://github.com/JetBrains/skiko/blob/master/LICENSE) use Apache-2.0, with separate third-party notices where applicable. [Skia](https://github.com/google/skia/blob/main/LICENSE), its enabled dependencies, bundled fonts, and any packaged Java runtime retain their own terms. The exact selected source graph, toolchain and runtime distribution are not yet pinned or reviewed; no Compose library or Linux runtime is included in the current product. Review these components before adoption and packaging under the [source dependency policy](architecture/dependencies.md).

## License texts

- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
- [MIT License](https://spdx.org/licenses/MIT.html).
- [Blue Oak Model License 1.0.0](https://blueoakcouncil.org/license/1.0.0).
- [BSD 3-Clause](https://spdx.org/licenses/BSD-3-Clause.html).
- [Pinned libVLC license](https://github.com/videolan/vlc/blob/6de05adcbaf2e8b85fe86aad4169393098628119/COPYING.LIB).
