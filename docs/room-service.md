# Running the room service

The room metadata service uses .NET SDK 10.0.402 and the ASP.NET Core shared framework. It is independent of the desktop UI and has no registry packages. Its [architecture and API](architecture/room-service.md) describe authorization, catalogs, replay, and limits.

## Build and check

Run from the repository root:

```sh
git submodule update --init --checkout --depth=1 -- 3rdparty/fastjsonschema
python3 tools/server/check.py --provision
```

On Windows use `python`. With an existing SDK, omit `--provision` or pass `--dotnet <path-to-dotnet>`. This checks the exact version, restores SDK/local references with the empty registry configuration, checks formatting, builds, runs real HTTP/WebSocket tests, and validates emitted events/snapshots with the pinned contract validator. `--provision` obtains a missing SDK from the official archive pinned by SHA-512 in [the manifest](../tools/server/toolchains.json).

Equivalent build commands are:

```sh
dotnet restore services/room-metadata/RoomMetadata.slnx --configfile NuGet.Config
dotnet format services/room-metadata/RoomMetadata.slnx --no-restore --verify-no-changes
dotnet build services/room-metadata/RoomMetadata.slnx --no-restore --configuration Debug
```

## Local startup

Generate a private creation key in the process environment. For a POSIX shell:

```sh
export SYNCWATCH_CREATE_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
dotnet run --project services/room-metadata/RoomMetadata --no-launch-profile
```

For Windows PowerShell:

```powershell
$env:SYNCWATCH_CREATE_KEY = python -c "import secrets; print(secrets.token_hex(32))"
dotnet run --project services/room-metadata/RoomMetadata --no-launch-profile
```

The default address is `http://127.0.0.1:8788`. `GET /health` reports liveness. The creation key must contain 32–256 characters; there is no built-in credential. Creation uses this key in an Authorization header. Member operations use their separate admission credential. The application does not print credentials, invitations, meeting links, or request bodies.

## Hosting and configuration

Use standard ASP.NET Core URL and Kestrel certificate configuration for HTTPS. HTTP is accepted only when both ends are loopback. A forwarding proxy does not enable external plaintext access: forwarded headers are not trusted. Browser-origin access and cookie/query-string authentication are disabled.

Configuration under `SyncWatch:Limits` adjusts validated bounds. Environment variable examples are `SyncWatch__Limits__MaximumRooms`, `SyncWatch__Limits__MaximumMembers`, and `SyncWatch__Limits__CatalogItems`. Durations such as `SyncWatch__Limits__RoomLifetime` use TimeSpan format. Invalid limits prevent startup. Defaults are listed in the [architecture](architecture/room-service.md#resource-bounds-and-storage).

Stopping/restarting discards rooms, credentials, catalogs, and history. This service does not start Syncplay, join Meet, or open movies. A successful health check does not establish those connections.
