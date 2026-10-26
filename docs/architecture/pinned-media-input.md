# Loaded media identity

Status: native input ownership, VLC binding and client hashing implemented. Normal shared playback admission remains disabled.

The native player and descriptor preparation read one pinned local input. Matching duration, size and modification time alone does not establish that independently opened paths read the same file version. A replacement or an in-place write must invalidate the prepared descriptor.

`packages/playback-native/src/media_input.c` supplies regular-file ownership, bounded positional reads and local version validation. POSIX detects handle/path replacement and change metadata even when size and modification time are restored; invalidation latches. Windows holds read-only handles that exclude writers and replacement, including a separate read position for hashing. Both paths release their handles explicitly.

The player passes the owned descriptor to the pinned public VLC file-descriptor API and releases it only after stopping and detaching media. Every observation or scoped command validates the input. A changed input stops and becomes failed; restoring the path cannot revive that generation. Generation-scoped native version/read calls expose local content without leaking paths or descriptor ownership. Regular observations provide validation; this does not implement an independent filesystem watcher.

## Ownership boundary

A small first-party native file-input module should own a read-only regular-file handle independently of the VLC runtime. The player retains that input until native stop and media release complete. VLC and descriptor hashing must read the same pinned file object; neither operation may independently resolve an unverified replacement path. Paths, file identities, version stamps and operating-system handles stay local.

Prefer the pinned VLC public file-descriptor API over callbacks into Swift, C# or the JVM from decoder threads. The Windows bridge and VLC must use compatible CRT descriptor ownership; verify that boundary against the pinned native toolchain before adopting it. The existing bridge owns the engine integration. Filesystem validation and input ownership belong in a separate source module, without UI, network or synchronization dependencies.

Provide bounded positional reads for hashing without changing VLC's read position. POSIX reads can address the pinned descriptor directly. Windows may need a separate read handle to the identical file object, protected against replacement and concurrent writes for the full playback lifetime. The shared input module must validate this identity rather than assume that reopening a path is equivalent.

## Native clients and hashing

Swift on macOS, Kotlin on Linux and C# on Windows implement separate `LoadedMediaContentPort` interfaces through their existing serialized native owners. `LoadedMediaVersion` is immutable local equality evidence scoped to the client run and media generation. Its stamp is private, redacted and excluded from room DTOs. The port returns bounded chunks from the player's pinned input without exposing descriptor ownership.

The Library hash component accepts a bounded asynchronous chunk reader and retains its platform crypto implementation. It has no dependency on the player, domain or room modules and opens no path in this mode. It rejects premature EOF, oversized responses and trailing bytes. The existing path-based catalog hash entry remains available for independent local-library work.

Shared media preparation retains the selected folder grant, reads and compares the native version before and after hashing, validates the observed duration, and retains the prepared version. The playback coordinator revalidates it immediately before transferring a synchronization transport. Cancellation, terminal close, stale generations or changed inputs reject the operation. Hashing, media input, room membership and admission remain independently owned components.

Validate regular-file identity and version before reading, after hashing and immediately before admission. On systems permitting concurrent file changes, compare handle and path identity, change metadata and modification metadata, and invalidate on filesystem changes or lost observation. Restoring size or modification time must not preserve an old authorization. Do not describe metadata checks as immutable storage or proof against an adversary controlling the filesystem.

An invalidated input clears the prepared descriptor and readiness and prevents further synchronized activation. Preserve room membership so the user can select valid media again. Existing agreed playback and metadata transport failure retain their separately defined recovery policy. File handling must not publish paths or turn metadata events into remote player commands.

## Delivery and acceptance

Implement each stage for all three clients together: native input ownership and bindings; hashing and loaded-version validation; workspace invalidation and normal room admission. A stage's tests do not qualify the later stages.

Exercise replacement between load and hash, same-length writes with restored modification time, mutation during hashing, unlink/rename, symlink and directory rejection, Unicode paths, stale generations, cancellation and repeated close. Verify that positional hashing does not disturb VLC playback or seek behavior. Test Windows write/delete exclusion and POSIX invalidation using actual native filesystem operations.

Run equivalent checks only on the target OS. Complete real GUI regression on all three desktops and all six applicable directed playback cases before qualifying normal shared admission. Reuse verified engine/runtime packages and one current build per platform; release file handles, apps, helpers, service and tunnels after each test group. No new external library or media-file copy is required by this design.
