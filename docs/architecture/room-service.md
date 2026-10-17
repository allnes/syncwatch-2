# Room metadata service

The ASP.NET Core executable in `services/room-metadata/RoomMetadata` manages ephemeral room metadata using only platform SDK libraries. It does not connect to Syncplay, play media, transport movie bytes, or participate in Meet. The native clients are not yet connected. See [running the service](../room-service.md).

## Authorization and lifetime

Room creation requires a configured creation key in an `Authorization: Bearer` header. Creation returns an owner membership credential and a separate invitation. Joining exchanges the invitation for a new member ID and credential. Credentials and invitations contain 256 random bits; the service retains hashes instead of their original values. Creation credentials do not authorize room access; member credentials cannot create rooms or access another room.

Members bind a server-issued ID to a declared process run ID and a unique Syncplay username. Events use this binding rather than caller-supplied member IDs. This reserves a metadata identity; confirmation of the username actually accepted by Syncplay belongs to native bridge integration.

Owners can rotate invitations and revoke members. Rotation invalidates the preceding invitation; revocation removes that membership's catalogs and immediately stops its stream. Leaving removes the caller. Owner departure closes the room and invalidates all access. A valid invitation permits a new membership, not reuse of a revoked token.

Defaults are an eight-hour room lifetime, 15-minute invitation lifetime, and 30-second initial-connect/reconnect grace. Disconnect retains membership and catalogs during the grace, then cleanup removes them. Expiry and shutdown cancel active streams. Restart discards rooms, credentials, and replay history; a newly created room has a new ID and epoch.

## HTTP API v1

Bodies are UTF-8 JSON bounded to 64 KiB, with exact fields and integer `v: 1`. Unknown fields, duplicate keys, unsupported versions, and oversized input are rejected. Credentials use headers or the join body, never query strings or cookies. Browser-origin access is disabled. Non-loopback connections require HTTPS; forwarded headers cannot bypass this check.

| Endpoint | Authorization | Request / response |
|---|---|---|
| `POST /v1/rooms` | Creation key | `v`, `clientRunId`, `syncplayUsername`, `syncplayHost`, `syncplayPort`, `syncplayRoom`; returns owner admission |
| `POST /v1/rooms/{id}/join` | Invitation in body | `v`, `invitation`, `clientRunId`, `syncplayUsername`; returns member admission |
| `GET /v1/rooms/{id}/snapshot` | Member | Bootstrap: room snapshot, TLS-required Syncplay binding, missing members, catalog cursor |
| `GET /v1/rooms/{id}/catalog?cursor=...` | Member | Up to 100 descriptors, snapshot sequence, next cursor |
| `POST /v1/rooms/{id}/commands` | Member | Metadata command and result |
| `POST /v1/rooms/{id}/invitation` | Owner | Rotate invitation; return invitation and expiry |
| `POST /v1/rooms/{id}/revoke` | Owner | `v`, `memberId`; remove that member |
| `POST /v1/rooms/{id}/leave` | Member | Remove caller; no body |
| `GET /v1/rooms/{id}/events` | Member | WebSocket; optional `epoch` and `cursor` request replay |
| `GET /health` | None | Liveness without room data |

Admission fields are `roomId`, `memberId`, `token`, `expiresAt`, `bootstrap`, and the owner's invitation (null for guests). The bootstrap contains a [v1 snapshot](../../contracts/v1/room-snapshot.schema.json), connection binding, missing-member IDs, and a catalog cursor. Returned credentials and invitations are private application data.

Catalog pages are stable at the bootstrap sequence. Their cursor expires after 60 seconds or a newer bootstrap for the same member. Fetch pages, then replay events after that sequence. A replay gap requires a new bootstrap and discarding obsolete partial state.

## Commands and ordering

HTTP and WebSocket commands share this envelope:

```json
{"v":1,"id":"cmd-1","type":"selection.changed","clientRunId":"run-1","roomEpoch":"epoch-1","watchGeneration":0,"payload":{"mediaId":"movie-a"}}
```

`watchGeneration` is the expected current generation. The server allocates sequence numbers and advances the generation for selection/start/end metadata. Competing selections from the same generation cannot both succeed. Media IDs refer to published catalogs, not filesystem paths.

| Type | Payload |
|---|---|
| `catalog.updated` | `batchId`, zero-based `offset`, `items` (at most 100), `final` |
| `selection.changed` | `mediaId` |
| `watch.started` | `mediaId` matching the selected or ended watch |
| `watch.ended` | Owner-only `reason`: `user` or `finished` |
| `media.missing` | Selected `mediaId`, boolean `missing` |
| `call.linkChanged` | Owner-only `meetUri`: canonical Meet URL or null |

Descriptors follow the [shared media schema](../../contracts/v1/media-descriptor.schema.json), including NFC and ASCII-only title-key folding. A catalog stages privately until its final command; offsets reject missing/reordered parts. The committed catalog replaces the member's preceding catalog and is published in bounded `catalog.updated` events without the command-only offset. Clients retain partial event assembly alongside a resume cursor, or advance a durable cursor only at the final catalog event.

[V1 room events](../../contracts/v1/room-event.schema.json) are direct WebSocket JSON messages. Initial connections receive `{"v":1,"type":"room.bootstrap","data":...}`. Results use `{"v":1,"type":"command.result","id":...,"sequence":...,"error":null}`; rejected transitions set the error string. Parsing/authorization failures use `room.error` with `error.code`. HTTP errors return a 4xx status and `error.code`; internal failures expose no input values.

Command IDs increase per membership within the shared integer bound. Exact-byte retries of the last 128 commands return retained results. Changed content under the same ID conflicts; evicted older IDs are rejected. Replay retains at most 256 events and 1 MiB per room. Gaps or replay exceeding the stream queue require a snapshot. Slow consumers disconnect instead of losing ordered events silently.

This API rejects play, pause, seek, speed, volume, camera, and arbitrary settings commands. Watch lifecycle events are bookkeeping and do not authorize remote player start, stop, or close. A Meet URL does not join a call or open audio.

## Resource bounds and storage

Defaults are 16 rooms, eight members per room, 256 catalog items per member, 32 queued frames per stream, 32 commands per second per member, and 128 concurrent HTTP/upgraded connections. Outbound messages are bounded to 64 KiB. State is in memory, without a database, account store, durable replay log, or filesystem access. Native media identity, Syncplay, and Meet integrations remain separate components.
