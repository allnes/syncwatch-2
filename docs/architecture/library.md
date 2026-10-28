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

The Library-to-WatchSession workflow captures the selected local media and its folder-access owner before starting playback. The watch owner retains that access independently of subsequent Library scans and selections until native release. Selected-file inspection is described below; sidecar extraction and filesystem watching still require their application integration. On macOS, the access adapter renews stale/moved bookmarks while access is active and reports denied/corrupt grants. A saved path cannot silently replace a failed grant. Windows and Linux retain their own explicit folder selection and revalidate access after restart. These local grant records are separate from the preference/resume format, which deliberately contains no paths or permissions.

The shared Library presentation receives entries and observed capabilities. It performs no filesystem work and starts no media provider. Application controllers map actual catalog state and selection into that presentation; only the existing WatchSession owner allocates or releases watch playback generations. A completed scan supplies a new revision and immutable local file facts to the separate [room publisher](../room-client.md#local-catalog-publication). That owner converts them to path-free descriptors and publishes only while membership is connected. Scanning and catalog exchange do not enable shared playback or establish practical readiness.

## Selected-file inspection

The library packages define a metadata-reader port and validated local facts:
optional duration, video dimensions, audio/embedded-subtitle track counts and
optional ordered raw track names. Unknown names and a known empty list remain
distinct; supplied lists must match their counts and are immutable snapshots.
They have no media-engine dependency. Each native application composes that
port with one serialized, silent, paused VLC owner, separate from its watch
player and synchronization helper. Inspection does not render video, play audio,
start a watch or advance the catalog revision published to a room.

A reader retains the selected folder grant, validates the loaded input against
the catalog size and waits up to three seconds for native observations. Before
returning facts it rechecks the loaded version and current filesystem size and
modification time. Invalid, missing or observably changed media is unavailable;
these checks do not claim an immutable snapshot or replace watch admission.
Every success, failure and cancellation releases the native input. Application
shutdown cancels and awaits inspection before closing its reusable VLC owner.

Controllers cancel obsolete selections, serialize replacement reads and reject
late results even when a provider ignores cancellation. Refresh and restart
inspect the current selected file again. The common Apache-2.0 Design package
owns loading/error copy and duration, resolution and no-subtitle formatting;
applications supply raw observations only. Unavailable metadata stays inline
and leaves the catalog usable. A local track draft belongs to one completed
metadata generation. It starts with the first audio stream and subtitles off,
correlates menu requests by source/revision, and resets on selection, refresh,
failure and close. Choosing a draft never advances the room catalog revision.
Start captures the draft together with the file/access owner. Native IDs from
the inspector are discarded; the new playback input must expose the same ordered
raw names before an ordinal resolves to its own current ID. A changed/reordered
list rejects admission rather than silently choosing a different stream.

Both lists are validated before either local command is submitted. Actual VLC
selected-ID acknowledgement precedes the loaded callback, watch controls and
shared admission. Cancellation/close interrupts this preparation. Home/Continue
retains the live input; its Library presentation disables draft selectors for
that same movie. External subtitle association remains separate integration work.

## Whole-library duration observations

A completed scan schedules the selected file first, then the other files in display
order through the same single silent inspector. A new selection cancels that work,
awaits native release and takes priority. Failures remain local to their row and do
not prevent inspection of later files or overwrite the selected card and track draft.
Background results cannot advance the room catalog revision. Close cancels and awaits
the entire inspection chain while retaining its folder grant through native release.

`LibraryDurationCache` belongs to the local library package. It stores at most256
positive duration observations in memory, evicting the oldest observation. Its key
is the complete scanned file version (root-scoped ID, path, size and modification
time). Reconciliation removes missing or changed entries; unknown modification
time is never reused across scans. Failed/unknown reads remove a prior duration.
The cache stores no tracks, native IDs, grants, digests or room credentials. Each
selected file is inspected afresh even on a cache hit, so current track preparation
and retry semantics stay independent of display hints. Background cache hits avoid
repeat probes; evicted rows may be inspected again on a later scan. Nothing is
persisted, and restart reconstructs observations from the authorized library.

The common Design entry accepts optional milliseconds. Its shared localized format
and declarative row layout show a trailing hour:minute duration only when positive,
without changing sorting, search or selection. Platform controllers supply facts;
they do not format labels or specify row geometry.

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

The application-owned `RoomWatchCoordinator` connects normal room Start to
paused native loading, preparation of that exact loaded input, acknowledged
opaque catalog publication, frozen selection/generation validation and the
verified helper package. An active watch admits a matching local edition
without starting another metadata generation. Only exact accepted Syncplay
identity and readiness release the shared playback controls. End, Leave and
application close release their own helper before the native playback owner.

This workflow is under qualification. Native controller/transport checks run
on all three target operating systems. Metadata interruption, end bookkeeping,
file completion and the complete directed playback matrix must pass actual
application checks before the feature is qualified. Explicit edition
confirmation, file watching and persistent digest-cache invalidation remain
integration work.
