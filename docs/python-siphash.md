# CPython SipHash correspondence

`cpython-siphash` records the selected SipHash embedded origin for CPython 3.12.15 and verifies its original raw native functions on macOS arm64, Windows x64 and Linux x64. It produces a source/provenance package and native transcript report, with no interpreter or embedding ABI.

## Source and module boundary

The [profile](../tools/python-siphash/profile.json) selects seven unchanged CPython files and three original files from the separately pinned [csiphash source](https://github.com/majek/csiphash). Complete original PSF/historical grants and MIT license/copyright/inspiration credits accompany all selected sources. The original CPython modifications remain intact; its code is not byte-identical to the earlier origin. The origin implementation and its POSIX test driver are reference inputs. Only the exact CPython pointer/size typedefs, algorithm constants and SipHash13/SipHash24/_Py_KeyedHash fragments enter the native probe.

The enabled graph preserves CPython's memcpy loads, C89/MSVC/endian handling and SipHash13 variant. Explicit first-party fixture configuration selects the supported 64-bit little-endian targets and compiles both original variants. It does not modify original source/algorithms. Full Python hashing, FNV, small-string DJBX33A, numeric/pointer hashing, runtime entropy, 32-bit/big-endian execution and the interpreter ABI remain outside this component.

`tools/python-siphash` separates source/profile validation, independent oracle/corpus, native fragment assembly and payload/cache verification. `tools/native/c_probe.py` owns disposable C SDK compilation/execution and transcript comparison; the Unicode component uses the same harness. Developer Python runs build tools only. No Python C SDK header/runtime is linked by either raw-source proof.

## Independent and native checks

A first-party integer model is validated by all 64 original SipHash24 known answers and ten original CPython seeded SipHash13/24 answers, without calling the SDK hash function or executing upstream test modules. Original deterministic test-seed context is retained; public fixture keys are not application entropy.

The frozen corpus covers six keys, two message patterns, 265 lengths through 4097 bytes, all eight 64-bit alignment offsets, zero-length/null input and the original seeded non-ASCII storage examples. A native executable evaluates 25,480 cases and emits 76,440 results for the two raw variants and keyed wrapper. Its fixed big-endian transcript must match the independently calculated frozen digest and size. These are known-answer/source correspondence checks for the selected corpus, not a proof of complete Python hashing or cryptographic certification.

## Build and artifacts

Use the native target and the installed C SDK (Windows uses `python` and Visual Studio):

```sh
python3 tools/dependencies/build.py build --component cpython-siphash --platform macos-arm64 --cold
python3 tools/dependencies/build.py build --component cpython-siphash --platform macos-arm64
python3 -m unittest discover -s tools/python-siphash/tests -v
```

Both cold and restored-cache paths recompute source/notice/corpus/oracle analysis, freshly compile/run the original functions and compare every payload byte. Cached reports alone are insufficient. Source, corpus and transcript digests agree across targets; SDK provenance differs by platform.

The payload retains unchanged original sources.zip, full notices, source/fragment/known-answer analysis, a separate selection/configuration/modification summary and measured native proof. No SDK, native test executable/library, interpreter or bytecode is distributed. Full native-core/other-origin and frozen/stdlib closure, a source-built interpreter/embedding ABI, authenticated immutable installation/loading and Syncplay/TLS integration remain independent requirements.
