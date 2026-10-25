# Local watch state

`WatchSession` in the Swift, C# and Kotlin domain packages owns local media selection, resource generations, navigation, and resume positions. It depends only on the platform SDK. The application serializes access; VLC, synchronization, room, and UI adapters remain separate.

## Lifecycle and resource effects

| Operation | Result |
|---|---|
| Select a different media ID | Release any previous local owner, invalidate pending work, and select the saved position |
| Start | Allocate a new generation and return one `load` effect with the media ID and position |
| Repeat Start while preparing or active | Present the player without allocating another owner |
| Loaded | Accept only the current preparing generation; retain paused state |
| Return to library / Continue | Change presentation while retaining the same media owner |
| Record playback | Retain the engine's actual position and pause state, including seeks while paused |
| Cancel preparation / End | Return a `release` effect for the owned generation, invalidate callbacks, and retain the resume position |
| Repeat End | Return no further resource work |

Effects describe local resource ownership. They do not send network commands or directly operate a player. The adapter releases both movie and preview resources for a released owner. It reports load failures through cancellation and rejects callbacks after release. Media loading alone does not permit synchronized playback; readiness belongs to the synchronization adapter.

Callbacks carry the `PlaybackScope` that initiated their work. A different process run is `foreignRun`; an obsolete local generation is `staleGeneration`. Rejected transitions leave state unchanged. The local counter is independent of the server's watch generation. Position and duration use integer milliseconds in the [shared contract bounds](contracts.md).

## Local settings and resume format

`LocalState` version 1 contains preferences, an optional selected logical media ID, and up to 256 resume entries ordered by their most recent update. Updating a movie moves it to the end; a new entry at capacity evicts the least recently updated one. Duplicate IDs and out-of-range positions are invalid. Absolute file paths, folder grants, process identities, active sessions, calls, invitations, and credentials are absent from this format.

| Preference | Initial value | Accepted values |
|---|---|---|
| Theme / language | `system` / `en` | `system`, `dark`, `light` / `en`, `ru` |
| Skip interval | 10 seconds | Integer 1–600 seconds |
| Timeline previews / cache | Enabled / 150 MB | Boolean / integer 50–500 MB |
| Cursor hide delay | 2500 ms | Integer 500–10000 ms |
| Movie / call volume | 1 / 1 | Finite values from 0 to 1 |
| Remember movie volume | Enabled | Boolean |
| Movie ducking | Disabled | Boolean |
| Camera / microphone preference | Enabled / enabled | Boolean |

These are stored local preferences. Saving them does not operate a camera, microphone, audio output, network connection, or media engine. The native application-settings dialog applies and persists language/theme while preserving the rest of the stored state. Other preferences await their UI and service adapters. Image/subtitle settings, device identifiers, folder grants, and window geometry are outside the initial persisted model.

On application restart, a fresh process scope is allocated and saved media becomes selected, paused, and hidden. A resume position never reactivates a session, loads media, joins a call, or grants filesystem access.

## Persistence port

`LocalStateStore` / `ILocalStateStore` separates storage from the coordinator. `FileLocalStateStore` accepts a caller-selected application-owned file under Application Support on macOS, LocalAppData on Windows, or the XDG state directory on Linux. It reads at most 64 KiB and reports missing, loaded, invalid, or unsupported-version state. Read errors such as access denial propagate to the caller; malformed or unsupported files are left untouched.

Writes validate and encode the complete state before replacing the destination atomically. The temporary file is on the same filesystem; unsuccessful writes do not publish a partial JSON document. The application serializes store access. This is atomic replacement, not a cross-process transaction or a guarantee against power loss. An older client refuses to overwrite a recognized future format. Recovery from invalid state is an explicit caller action.

All three implementations consume [the same local-domain corpus](../../contracts/fixtures/local-domain.json) through their existing native test entry points in [building and running](../building.md). This local format is independent of the versioned network/IPC schemas.
