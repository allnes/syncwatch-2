# Kotlin standard-library sources

The `kotlin-stdlib-sources` component produces a deterministic source ZIP for the selected JVM standard-library profile. It uses Python 3.12 or newer and Git, without a Kotlin compiler, Gradle, Maven or registry libraries.

## Pinned inputs

| Source | Pin | Selected content |
|---|---|---|
| `3rdparty/kotlin-stdlib` | Kotlin `v2.3.20`, `d57eb4a26ed01ab03cf195da686c8047032ff16f` | 478 unmodified files, including 416 prospective stdlib inputs, 48 Unicode generator references, module/build documentation and full notices |
| `3rdparty/unicode-data` | Unicode tools `release-20210720-u13`, `84a95001ba850554e65234dde62cbdb0ad41105a` | `UnicodeData.txt`, `SpecialCasing.txt`, original license and README |

The [source profile](../tools/jvm/stdlib_sources.json) records every selected file digest, source role, export root and notice. The stdlib inputs comprise 202 common Kotlin files, 209 JVM Kotlin/Java files, four compile-only declarations and one Java module descriptor. Generator and Gradle files are retained references; they are not executed. No native sources or fonts are selected.

The Unicode tools repository warns against using its development data in production. The two selected Git blobs were independently compared byte for byte to the [published Unicode 13.0.0 UCD archive](https://www.unicode.org/Public/zipped/13.0.0/UCD.zip), SHA-256 `2f76973b4d36ae45584f5a45ec65b47138932d777dd23a5669c89535ef3da951`. Their digests and publication provenance are fixed in the profile; builds use only the pinned Git sources and do not download the archive.

## Build and verify

Run from the repository root, choosing `macos-arm64`, `linux-x64` or `windows-x64` for the host:

```sh
python3 tools/dependencies/build.py build --component kotlin-stdlib-sources --platform macos-arm64 --cold
python3 tools/dependencies/build.py build --component kotlin-stdlib-sources --platform macos-arm64
python3 tools/jvm/stdlib_sources.py verify --platform macos-arm64
python3 -m unittest discover -s tools/jvm/tests -v
```

On Windows, use `python` instead of `python3`. Source preparation may fetch the exact Git pins. Packaging and verification use the prepared snapshots offline. Both cold builds and cache reuse reconstruct the expected ZIP and compare every payload byte, including notices and the inventory. Unexpected, modified or missing files fail verification.

The payload contains `kotlin-stdlib-2.3.20-syncwatch-sources.zip`, `source-inventory.json`, `unicode-provenance.json`, `THIRD-PARTY-NOTICES.txt` and unchanged upstream notices. The ZIP retains all selected original files under `kotlin-stdlib/` and `unicode-data/`, with the same metadata/notices under `META-INF/`. Entry order, timestamps, modes and stored bytes are deterministic across platforms.

## Unicode correspondence

The verifier evaluates the pinned titlecase builder's rules using Unicode 13 data, independently of Python's or the host JVM's Unicode version. It skips contextual rules and mappings derivable from simple case conversion, verifies the ten remaining mappings, applies the upstream Greek Extended filtering rule, and checks the apostrophe-n case and committed Kotlin function. This establishes correspondence for the common/JVM titlecase generator. Other committed generated sources are preserved and hash-checked without regeneration.

## Licenses and scope

The selected Kotlin code uses Apache-2.0, with GWT/Guava attributions, BSD-3-Clause ThreeTenBP-derived time code and BSL-1.0 Boost-derived math fragments. Full original license texts, COPYRIGHT, NOTICE, license README and source headers accompany the source ZIP and payload. The original upstream NOTICE retains its compiler-distribution wording. Of 464 Kotlin/Java files, 462 have Apache block headers; the module descriptor and `ExperimentalStdlibApi.kt` use the repository-wide declaration. No original copyright is synthesized or upstream source changed.

Unicode's pinned notice is the Unicode-DFS-2016 permission form, retained in full with its original copyright and the SpecialCasing attribution. A newer Unicode license is not substituted for it. Preserve these notices and applicable name/endorsement restrictions when redistributing sources or derived reports. The Python correspondence verifier identifies its adapted upstream logic and changes in its source header.

This component provides sources only. It produces no stdlib binary or runnable Linux client, provisions no compiler SDK and includes no JVM runtime. The upstream `KotlinVersion(2, 3, 255)` placeholder is preserved. Binary compilation, version patching, Java/JPMS assembly, API/metadata compatibility, the compiler's embedded license graph, Compose/native/font closure and any packaged JVM require their own completed profiles. `linux-compose-ui` remains unavailable.
