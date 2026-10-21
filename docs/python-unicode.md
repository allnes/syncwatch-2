# Unicode type tables

`cpython-unicode-types` closes the selected Unicode 15.0 input graph for CPython 3.12.15 character type tables. It produces a source/data package and an exhaustive native table verification report on macOS arm64, Windows x64 and Linux x64. It does not provide a Python interpreter, embedding ABI, complete Unicode library or Syncplay runtime.

## Source boundary

The [profile](../tools/python-unicode/profile.json) selects six unchanged CPython files and sixteen unchanged Unicode files at exact Git revisions. CPython supplies its original generator, checked-in table, native helper, public Unicode header and full notices. A separate `3rdparty/python-unicode-data` submodule supplies Unicode 15.0 data; the Kotlin Unicode 13 source remains independent.

The selected source graph excludes Unicode name/normalization generators, old-version tables, CLDR/ICU, Java tools and other native interpreter origins. Developer Python and the installed C SDK run build and verification tools only; neither supplies Unicode oracle data nor enters this payload. No Python SDK headers or runtime are linked by the native table probe.

The original Unicode-tools README recommends the published Unicode.org production data. Selected ordinary UCD files match the versioned production UCD archive byte for byte. The 73 expanded Unihan numeric property rows match the published combined numeric data. Builds use only the pinned Git source snapshots; they never download or substitute a canonical archive.

## Generation and verification

The original CPython generator runs in an isolated, timed child with owned, whitelisted input/output ports. It selects Unicode 15.0 and the original logical script label. Its output writer creates ASCII/LF bytes directly. Unknown inputs, versions, repeated reads and unexpected outputs fail; network and subprocess operations are denied during generation. Original source and algorithms remain unchanged.

The Git input stores Unihan numeric properties in three range-compressed files. An explicit first-party adapter expands them into a separately labelled interchange and a stored in-memory ZIP for the original generator reader. The original files remain intact in `sources.zip`. The complete generated header must match CPython's original checked-in header byte for byte, including its generation notice.

The independent oracle parses the original checked-in type records and two-level indices, raw UnicodeData numeric/category/bidirectional properties, LineBreak properties and original Unihan numeric rows. It does not call the generator or the developer SDK Unicode database. A disposable C SDK executable compiles exact original public-type, record-type and lookup fragments with the reproduced table and its original numeric/space/linebreak functions. It emits a fixed big-endian transcript:

- Signature and record count.
- All 1,114,112 code-point slots, including surrogate and unassigned slots, followed by three out-of-range guards. Each record contains six unsigned 32-bit representations of the raw type fields, an IEEE binary64 numeric value, and unsigned 32-bit whitespace and linebreak results.
- The extended-case array count and every unsigned 32-bit value.

Both the independently calculated and executed transcript must match the frozen profile digest and length. Supported native SDKs must provide 8-bit bytes, 32-bit integers and IEEE binary64. This is exhaustive table correspondence for these fields/functions, not full interpreter API or ABI acceptance.

## Build and payload

Use the host's native target (`macos-arm64`, `windows-x64` or `linux-x64`):

```sh
python3 tools/dependencies/build.py build --component cpython-unicode-types --platform macos-arm64 --cold
python3 tools/dependencies/build.py build --component cpython-unicode-types --platform macos-arm64
python3 -m unittest discover -s tools/python-unicode/tests -v
```

Windows uses `python` and the installed Visual Studio C SDK. Both cold builds and restored-cache verification freshly regenerate the header, independently calculate the oracle, compile and execute a native probe, and verify every payload byte against the fresh result. Cache metadata alone is insufficient. Source/header/transcript digests are portable; SDK provenance varies by host, so complete payloads need not be identical across platforms.

The payload contains the reproduced header, unchanged original source archive, complete original grants/notices, clearly labelled derived Unihan interchange, selection/configuration summary and native/source report. It distributes no SDK, test executable, native interpreter or bytecode. Original PSF/historical, Secret Labs and Unicode notices and non-endorsement terms accompany the selected source and generated data. No original holder/year is replaced. Runtime adoption still requires closure of all other enabled native/frozen/stdlib origins, a source-built interpreter and embedding ABI, authenticated installation/native loading, and Syncplay/Twisted/TLS integration.
