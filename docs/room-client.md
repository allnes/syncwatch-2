# Native room clients

`packages/macos-room`, `packages/windows-room` and `packages/linux-room` own the native RoomMetadata connection. They use Foundation, .NET HTTP/WebSocket and JDK HTTP/WebSocket SDK APIs respectively. Swift builds and tests run only on macOS, C# only on Windows, and Kotlin only on Linux.

A client owns one room attempt. It creates or joins a room, immediately opens its event stream, validates the initial bootstrap against the admission, and retains that stream while preparing media. Membership reserves a declared Syncplay username; the playback bridge must separately verify the username accepted by Syncplay before publishing readiness.

The service address is an origin with HTTPS. Plain HTTP is accepted only for literal `127.0.0.1` or `::1`. Paths, credentials, query strings, fragments, redirects and cookies are rejected or disabled. Credentials remain memory-only and have redacted diagnostic descriptions; invitation copying requires an explicit action. Server error text is never presented as a trusted error message.

Responses and messages are bounded to 64 KiB. JSON rejects duplicate names, malformed UTF-8, excessive depth, noninteger counters and unknown admission/bootstrap fields. Admission verifies the caller's member/run/username binding, mandatory Syncplay TLS, watch consistency, unique member IDs/usernames and canonical Meet links. The event queue holds at most 32 messages and terminates on overflow. Callers must validate event payloads and ordering before applying them.

HTTP requests use bounded whole-response deadlines. The long-lived event transport has its own lifetime and must not inherit those short deadlines. Socket termination must release a waiting consumer even when the SDK does not complete an outstanding receive callback. Close cancels HTTP work, terminates the event stream and waits for owned operations. These APIs provide transport and validated bootstrap facts. They do not authorize media, establish a Syncplay connection or qualify a usable desktop room workflow. Workspace integration, event reduction/recovery and playback admission remain separate requirements.

The shared [room-client corpus](../contracts/fixtures/room-client.json) exercises admission/address rejection and redaction on each native OS. Live transport tests additionally create a room, attach the owner's stream, join and attach a guest, observe member binding/departure, read a snapshot, leave, close twice and reject subsequent work. Their owned service is supplied through `SYNCWATCH_ROOM_SERVICE` and `SYNCWATCH_ROOM_CREATION_KEY`; these variables are test inputs rather than desktop configuration.

## Workspace integration

Each native workspace owns its membership controller independently of the connection dialog. The common `packages/design/room.json` defines the form fields, limits and secure input kinds; `layouts.json` and the existing design tokens define its appearance. Native adapters translate input and clipboard actions without defining another visual design.

Create and join drafts remain in memory. Switching modes or closing the form clears secret fields. Dismissing an established connection's form retains membership. Leave and application close cancel the attempt, attempt a bounded departure and release owned network work. Event messages are ordering hints: controllers validate their envelope and fetch an authoritative snapshot before updating presence.

Copy invitation produces two lines: the room ID and its credential. Join exposes Paste invitation, which reads plain text through the platform clipboard adapter and validates the complete value in the room module. LF and CRLF are accepted; extra lines, whitespace, invalid identifiers and invalid credential bounds are rejected. Invalid input clears stale invitation fields. Pasting keeps the service address and display name explicit and starts no network work. Diagnostic descriptions of invitation objects remain redacted.

An unavailable system clipboard is a recoverable copy failure. Native adapters report the write result to the room controller, which shows shared localized feedback without changing membership or displaying exception details. The user can retry Copy invitation or leave the room.

## Local catalog publication

The Room SDKs read a frozen selected descriptor against an explicit bootstrap. They require the same epoch and watch generation, a nondecreasing sequence, and the selected media ID from that bootstrap. Descriptor validation is shared with catalog pages. A historical publishing member may have left. Basic membership and catalog refresh do not require this additive endpoint; shared admission must report an unsupported or unavailable endpoint as a recoverable setup failure.

The application membership session serializes watch-context reads and explicit metadata actions with catalog publication. Unknown command outcomes retain their original bytes and counter. An explicit user action keeps its expected generation: a peer change requires a new decision rather than an automatic overwrite. These operations expose metadata only; local media authorization, native-version revalidation and accepted Syncplay identity remain separate requirements.

The normal workspace feeds each completed Library scan to its membership controller. On connection, and after a new scan revision, one publisher replaces the member's catalog. Revisions arriving during publication coalesce into a subsequent replacement. Scans that fail do not publish a partial catalog. The shared Design package owns the localized publication and rescan feedback; publication failure preserves membership and the preceding complete view. Refreshing the folder retries with the latest completed scan.

`RoomMembershipSession` serializes authoritative snapshot/catalog walks and outgoing commands for one membership. Its command counter survives refreshes. If a response is lost, it retains the immutable command and resolves that same ID and body before sending a new replacement, even when local files changed in the meantime. An authoritative rejection consumes its command ID. A stale-generation rejection permits one new batch after reading fresh metadata; persistent rejection is surfaced rather than retried indefinitely.

`RoomLocalCatalog` maps private local identifiers to opaque room media IDs for the membership lifetime. IDs remain stable for retained entries and are discarded after acknowledged removal. Paths, folder grants and path-derived local IDs never enter descriptors. These initial descriptors contain title and size; they do not assert full hashes, duration, edition agreement or playback readiness.

Catalog commands contain at most 100 descriptors and at most 64 KiB, including their complete envelope. The publisher reduces each batch by encoded byte size and sends a final empty batch when clearing a catalog. It rejects local catalogs above the service's maximum of 2048 entries. The deployed service can impose a lower configured limit (256 by default); rejection remains visible and does not silently truncate the Library. Only complete acknowledged views replace application metadata. Leave and close cancel and join publication before releasing membership.

Native application tests cover identity mapping, Unicode byte limits and empty replacement. Opt-in live tests drive the normal controllers through publication, peer replacement and repeated close; a controlled response-loss case verifies replay of the same committed command before publishing changed local data. Run each client's checks only on its target OS.

Workspace integration remains in progress. Stream reconnection and shared playback admission require further acceptance. Membership does not authorize local playback: Start is withheld after any room attempt until the shared-watch coordinator is attached or the user explicitly leaves the room. A failed connection retains this gate and exposes Leave, preventing a silent return to local playback. Confirmed selection, the accepted Syncplay username and the loaded file version remain separate admission requirements.
