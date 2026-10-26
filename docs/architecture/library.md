# Local library ownership

The filesystem library is independent of design, playback, room metadata and synchronization. Swift, C# and Kotlin adapters live in `packages/macos-library`, `packages/windows-library` and `packages/linux-library`. They use platform SDK APIs and share the catalog corpus in `contracts/fixtures/library-catalog.json`.

## Discovery

`FileSystemLibrary` scans an absolute, already-authorized directory off the UI thread. The caller retains its access grant for the complete scan and any later playback. Optional recursive discovery accepts MKV, MP4, AVI, MOV, M4V, WEBM, WMV, MPG, MPEG, TS and M2TS extensions without case sensitivity. File names, relative paths, actual sizes and modification timestamps are filesystem facts. Empty files can be discovered; discovery does not claim that they are playable or provide invented metadata.

Nested symbolic links and Windows reparse points are excluded. Nonrecursive scans read the selected directory only. The adapter checks cancellation throughout traversal, closes enumeration resources and returns one completed, immutable snapshot. Filesystem failures propagate instead of publishing an incomplete replacement. The application must retain its previous catalog, distinguish missing/inaccessible roots, and ignore completions from obsolete selections.

Results are ordered by unsigned UTF-8 bytes of their exact relative paths with slash separators. The local media ID is lowercase SHA-256 of `UTF8(rootGrantID + NUL + relativePath)`. A root grant uses one persistent canonical lowercase UUID. Keeping the grant ID across a moved-folder restoration preserves relative identities; selecting a different library allocates its own namespace. The relative path preserves filesystem spelling rather than conflating distinct Unicode or case-sensitive files.

A path-derived local ID identifies a catalog entry, not a movie edition or content digest. Full paths and modification timestamps remain local. Peer descriptors require explicit conversion to the reviewed media schema; strong edition matching still requires the independent full-file hash and metadata rules in [Syncplay architecture](syncplay.md#media-identity).

The application captures a typed local selection from the current completed catalog. It retains both the discovered file facts and the folder-access owner. An active playback owner keeps this selection independently of later rescans, folder changes or Library disposal, and releases it only after native playback teardown. Scanning, empty and closed controllers provide no new selection. Display text and paths are never parsed back into authorization or media identity.

## Application boundary

`LibraryAccessStore` separates local persistence from application coordination. Its version1 record contains the platform, root UUID, absolute path, bookmark, recursive-scan and automatic-refresh preferences. Reads are bounded to256KiB and distinguish missing, loaded, invalid and unsupported-version data. Malformed data is left untouched by reads; recognized future versions cannot be overwritten. Writes validate before atomic replacement; callers serialize operations outside rendering. This is not a cross-process transaction.

`LibraryFolderAccess` revalidates a saved directory before use. On macOS it resolves the security-scoped bookmark without UI, retains read-only scoped access through the final reference, and renews moved/stale bookmark metadata under the same root UUID. The saved path is never a fallback for a corrupt grant. A current picker grant remains usable if bookmark creation fails, with persistence explicitly unavailable. Windows and Linux restore their explicit path and recheck current filesystem access; missing or denied roots remain errors.

The normal application Library now owns a native folder picker and a cancellable catalog controller on each platform. Startup restores the saved folder; selection, refresh and search use the common Library presentation. Only completed, current scans replace the last stable snapshot. Replacing an in-flight scan with a failing request restores the preceding catalog rather than leaving the UI busy. Persistence failures leave the current folder usable and show a localized message. Close cancels pending publication and serialized store work cannot overwrite a newer selection out of order.

The Library-to-WatchSession workflow captures the selected local media and its folder-access owner before starting playback. The watch owner retains that access independently of subsequent Library scans and selections until native release. Metadata/sidecar extraction and filesystem watching still require their application integration. On macOS, the access adapter renews stale/moved bookmarks while access is active and reports denied/corrupt grants. A saved path cannot silently replace a failed grant. Windows and Linux retain their own explicit folder selection and revalidate access after restart. These local grant records are separate from the preference/resume format, which deliberately contains no paths or permissions.

The shared Library presentation receives entries and observed capabilities. It performs no filesystem work and starts no media provider. Application controllers map actual catalog state and selection into that presentation; only the existing WatchSession owner allocates or releases playback generations. Scanning alone does not enable shared playback, publish a room catalog or establish practical readiness.

## Shared media preparation

The application retains its selected folder grant while a cancellable preparation
reads the local file in bounded chunks. SHA-256 uses platform SDK implementations;
the read checks the scanned size/modification facts and checks for observable
changes before publication. All handles close on success, failure or cancellation.
A new preparation reads the bytes again, including when a replacement preserves
size and modification time; no persistent digest cache is enabled yet. These
checks do not create an immutable filesystem snapshot. Preparation is canceled
and awaited before the native owner releases its selection.

`MediaDescriptor` in each domain contains only catalog facts, never a local path
or access grant. Its title key uses NFC, ASCII-space collapse and ASCII-only
case folding, matching the room service. `MediaAgreement` accepts at most 256
unique local IDs. A unique full SHA-256 match with consistent size and a positive
known duration can resolve automatically. Duplicate copies remain ambiguous;
missing hashes, unknown duration and other encodings require explicit edition
confirmation. Conflicting facts under the same full hash are rejected. A title,
size or duration alone cannot authorize automatic playback.

The native player exposes preparation for the room coordinator. The explicit
shared-session check consumes it, but normal room admission, background catalog
exchange, confirmation UI, file watching and persistent digest-cache invalidation
remain integration work.
