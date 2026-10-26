# Loaded media identity

Status: implementation proposal; normal shared playback admission remains disabled.

The native player currently opens a local path, while descriptor preparation opens that path again to compute its hash. Matching duration, size and modification time does not establish that these operations read the same file version. A replacement or an in-place write can invalidate an otherwise matching descriptor.

## Ownership boundary

A small first-party native file-input module should own a read-only regular-file handle independently of the VLC runtime. The player retains that input until native stop and media release complete. VLC and descriptor hashing must read the same pinned file object; neither operation may independently resolve an unverified replacement path. Paths, file identities, version stamps and operating-system handles stay local.

Prefer the pinned VLC public file-descriptor API over callbacks into Swift, C# or the JVM from decoder threads. The Windows bridge and VLC must use compatible CRT descriptor ownership; verify that boundary against the pinned native toolchain before adopting it. The existing bridge owns the engine integration. Filesystem validation and input ownership belong in a separate source module, without UI, network or synchronization dependencies.

Provide bounded positional reads for hashing without changing VLC's read position. POSIX reads can address the pinned descriptor directly. Windows may need a separate read handle to the identical file object, protected against replacement and concurrent writes for the full playback lifetime. The shared input module must validate this identity rather than assume that reopening a path is equivalent.

## Native clients and hashing

Swift on macOS, Kotlin on Linux and C# on Windows retain their platform hash implementations. A local content-reader port supplies bounded chunks from the player's pinned input and a scoped version stamp. Keep hashing, media input, room membership and shared-playback admission as separate components. Cancellation or player replacement invalidates outstanding preparation; a stale generation cannot publish a descriptor.

Validate regular-file identity and version before reading, after hashing and immediately before admission. On systems permitting concurrent file changes, compare handle and path identity, change metadata and modification metadata, and invalidate on filesystem changes or lost observation. Restoring size or modification time must not preserve an old authorization. Do not describe metadata checks as immutable storage or proof against an adversary controlling the filesystem.

An invalidated input clears the prepared descriptor and readiness and prevents further synchronized activation. Preserve room membership so the user can select valid media again. Existing agreed playback and metadata transport failure retain their separately defined recovery policy. File handling must not publish paths or turn metadata events into remote player commands.

## Delivery and acceptance

Implement each stage for all three clients together: native input ownership and bindings; hashing and loaded-version validation; workspace invalidation and normal room admission. A stage's tests do not qualify the later stages.

Exercise replacement between load and hash, same-length writes with restored modification time, mutation during hashing, unlink/rename, symlink and directory rejection, Unicode paths, stale generations, cancellation and repeated close. Verify that positional hashing does not disturb VLC playback or seek behavior. Test Windows write/delete exclusion and POSIX invalidation using actual native filesystem operations.

Run equivalent checks only on the target OS. Complete real GUI regression on all three desktops and all six applicable directed playback cases before qualifying normal shared admission. Reuse verified engine/runtime packages and one current build per platform; release file handles, apps, helpers, service and tunnels after each test group. No new external library or media-file copy is required by this proposal.
