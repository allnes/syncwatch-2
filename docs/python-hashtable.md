# CPython hashtable source package

`cpython-hashtable` records the selected cfuhash-derived origin for CPython 3.12.15 and verifies the original standalone implementation on macOS arm64, Windows x64 and Linux x64. It produces unchanged original sources, complete notices and a native correspondence report.

The [profile](../tools/python-hashtable/profile.json) selects seven unchanged CPython files and five reference files from the separately pinned libcfu Git submodule. Original PSF/historical, MIT and BSD-3-Clause grants accompany the selected files. The libcfu sources are reference/provenance only and are never compiled. CPython's original modifications remain intact; its implementation is not byte-identical to the earlier origin.

`tools/python-hashtable` separates source/profile validation, the independent dictionary oracle and public corpus, native source assembly and payload/cache verification. The common `tools/native/c_probe.py` owns a disposable strict C SDK build. The probe compiles the complete original hashtable declarations/body and exact pointer-hash/type/macro fragments with explicit first-party ISO C allocation/declaration ports. Assertions remain enforced. No Python C SDK or interpreter runtime is linked.

Four profiles exercise collisions, spread hashes, distinct-address equal keys and the original pointer-key dispatch. Each executes 2184 operations over 256 keys; all 8736 records must match the fixed portable dictionary transcript. Native checks cover null keys/values, missing entries, growth/shrink, returned values, steal versus destruction, clear/reuse, full and early-stop iteration. A tracked allocator separately injects one failure at every allocation in a fresh bounded grow/shrink/clear/reuse scenario and checks rollback, reuse, destructor counts and zero outstanding allocations.

Cold and restored-cache verification both freshly repeat source/notice/oracle checks and native execution before comparing every payload byte. No probe executable, native library, developer SDK, interpreter or bytecode is distributed. These bounded standalone algorithm checks do not verify interpreter allocation/thread lifecycle, a source-built runtime, embedding ABI or Syncplay startup. Remaining core/platform/bootstrap/TLS components retain their own gates.

Use the target matching the native host:

```sh
python3 tools/dependencies/build.py build --component cpython-hashtable --platform macos-arm64 --cold
python3 tools/dependencies/build.py build --component cpython-hashtable --platform macos-arm64
python3 -m unittest discover -s tools/python-hashtable/tests -v
```

Windows uses `python` and `windows-x64`; Linux uses `python3` and `linux-x64`.
