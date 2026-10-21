# Native Python package verification

The first-party `packages/python-package` C library validates a closed runtime directory against trusted native inventory data and maps accepted paths to the [shared startup contract](python-startup.md#native-helper-startup). The same implementation supports macOS arm64, Windows x64 and Linux x64. It is a prerequisite for a packaged Python helper; application startup is not wired to this module yet.

## Ownership and API

`sw_package_open(root, files, count, &package)` copies the canonical absolute root and every expected relative filename, byte size and SHA-256 digest. The inventory must come from authenticated, reviewed native application/package data. An inventory supplied by the unverified runtime directory is not a trust anchor. No external JSON manifest is parsed by this API.

The call publishes an owned immutable result only after a complete scan succeeds. `sw_package_resolve` returns declared file or directory paths from that accepted inventory. A failed query leaves the destination buffer unchanged. Empty directory selects the package root. `sw_package_close` releases the inventory after readers stop. Input strings remain valid throughout each call; results never borrow caller storage.

`sw_python_package_create_paths` validates a relative executable, native runtime library and ordered search list. The executable has an internal parent directory, keeping adjacent interpreter-configuration probes within the closed package tree. Search entries are declared directories or `.zip` files. The resulting owned object exposes the existing `sw_python_paths` structure and runtime library path, and remains valid after closing the inventory result. Home and all prefixes use the accepted root; executable fields use the accepted helper path. The module neither loads a library nor initializes Python.

Public headers contain the limits and typed status values. Relative names use portable ASCII components, `/` separators and strict ASCII case-folded ordering. Roots may contain Unicode. Duplicate/case-aliased names, inconsistent directory casing, file/directory overlap, traversal, device names, alternate path syntax and interpreter configuration such as `pyvenv.cfg`, `.pth`, `._pth` and customization modules are rejected. The complete actual tree must contain exactly the expected regular files and implied directories; empty extra directories are also rejected.

## Filesystem verification

The hash implementation is the source-built, namespaced [HACL static component](native-hashing.md). Size and streamed SHA-256 must match the expected file bytes. Hash state and buffers use bounded caller-owned storage; the wrapper calls the original reset/update/digest functions and avoids the upstream unchecked allocating constructor. Native static-library import inspection rejects a vendor allocator or any other unexpected HACL call. Every failure releases owned file/hash/directory state and returns a sanitized status, without reporting private paths.

On POSIX platforms, each root component is opened without following links. Child traversal uses directory-relative descriptors, no-follow metadata/opens and nonblocking file opens; symlinks, hard links, nonregular files and child filesystem crossings are rejected. File and directory metadata changes observed during verification fail the scan.

On Windows, ancestor and package opens inspect reparse points without following the final component. Junctions/reparse entries, hard links, named data streams, case aliases, remote drives and non-disk files are rejected. File reads use an owned handle and verify size, identity and metadata before and after hashing. All search and file handles close on failure as well as success.

This result records a completed scan. It is not an atomic filesystem snapshot, sandbox, authenticated installer or seal against a concurrently hostile writer. Resolution performs no new filesystem I/O and does not acknowledge later mutations. Package authenticity, source/binary/embedding-ABI identity, installation permissions and immutability, code signing and verification immediately before loading remain caller/release prerequisites. Filesystem ACLs, extended metadata and platform permissions are not treated as equivalent. Run verification in the owned helper under the parent's startup watchdog, away from the UI thread.

## Native checks

Use Python 3.12 or newer, CMake 3.30 or newer and the native C SDK described in [building](building.md). No registry package is installed.

```sh
python3 tools/python-package/package_probe.py --report artifacts/python-package/native.json
```

The command first freshly verifies the source-built HACL prerequisite. It compiles the actual static package library, links it into an owned temporary test module, and runs the public C API through developer Python/ctypes in a separate bounded process. The child exits before its temporary module is removed, including on Windows. The SDK, test module, fixture files and executable/library placeholders are not distributed or loaded as a Python runtime.

The 34 native API cases cover Unicode roots, SHA-256 chunk boundaries, immutable copied inputs, corrupt/truncated/extra/missing files, malformed and bounded inventories, aliases/links, exact path queries, startup layout and lifetime/handle release. POSIX FIFO and Windows named-stream cases run on their respective systems; real directory junctions are tested on Windows. Two additional regression cases check accepted symbol-tool formats and reject missing/unprefixed imports or a vendor allocator. Reports retain native SDK identity, HACL artifact identity, first-party source hashes, static/test binary hashes, complete case results and explicit readiness flags. Required CI compiles and executes these checks on all three platforms.

The full pinned CPython core/platform/stdlib and embedded-origin source/license graph, actual embedding ABI, authenticated immutable installation, Twisted/TLS/CA and Syncplay remain incomplete. This verifier does not enable the interpreter or synchronization. Linux Compose/compiler/native/font and actual GUI closure remain separate requirements.
