# Syncplay helper and native pipes

The development helper embeds the source-built CPython/Syncplay/TLS runtime in a dedicated process. The application owns that process and its inherited stdin/stdout pipes. It is a provider integration boundary, independent of shared design and window rendering. A controlled player can be attached before the native VLC provider is available.

`packages/ipc` owns strict schema validation, incremental framing and bounded command replay. The contract checker and helper use the same implementation. `packages/syncplay-helper` owns isolated native startup, pipe threads, one reactor/controller and the upstream-engine adapter. Syncplay retains all synchronization decisions. Native transports live in `packages/apple-bridge`, `packages/windows-bridge` and `packages/linux-bridge`; they contain no layout or playback policy.

The helper requires `bridge.hello` before work, fixes the process run and media generation, correlates results, rejects contradictory command reuse and retains completed results without executing duplicates. Each direction has an independent command sequence. Queues, frames and pending corrections are bounded. A full queue, an invalid stream, a missing acknowledgement or EOF terminates the owned scope. Native process owners enforce a bounded shutdown and terminate a helper that fails to exit. A failed provider must pause/release its native player through the application resource owner.

`player.loaded` supplies an opaque authorized handle and local filename/duration/size metadata. It authorizes no arbitrary path or network URL. `player.state` reports actual native observations. Its optional `origin` is `observation` by default; only explicit `user` observations may authorize the upstream user-change/send path. Other message families cannot claim that origin. Each user-origin observation carries a strictly increasing `actionSequence`. Corrections carry `afterUserAction`: the native owner rejects a correction older than its latest actual user action before mutating the player, then returns correlated `cancelled`. The helper accepts that cancellation only when the request is demonstrably superseded; other provider failures close the scope. Engine corrections are sent as `player.setPaused`, `player.setPosition`, `player.setSpeed` or `player.openFile`; a result is correlated with its correction and supplies actual pause/position with observation authority only. The helper keeps ping heartbeats but omits stale playstate while ordered native corrections await acknowledgement. Expected command values never become observations. Acknowledging connection initiation does not assert an authenticated connection. Readiness requires the initial canonical state and an observed ready player.

Media selection belongs to the application coordinator. The helper disables the stock shared-playlist controller through the pinned engine configuration so it cannot independently reopen or rewind an application-owned file. This does not disable upstream play/pause/seek, readiness, drift correction or transport recovery. Shared movie/playlist-item selection still requires the application selection and RoomMetadata integration.

The current helper accepts public trusted TLS endpoints. `secretHandle` fails as unavailable until the application credential broker is attached. Standard output contains protocol frames only. Upstream console text is suppressed; native adapters discard diagnostics without accumulating them.

Build and exercise a previously source-built engine payload:

```sh
python3 tools/bridge/check.py --runtime artifacts/dependencies/syncplay-runtime/macos-arm64/payload --output artifacts/helper/macos-arm64
python3 -m unittest discover -s tools/bridge/tests -v
swift run --package-path packages/apple-bridge BridgeProbe /absolute/helper/bin/syncwatch-helper /absolute/helper
dotnet run --project packages/windows-bridge/SyncWatch.Bridge.Probe -- /absolute/helper/bin/syncwatch-helper /absolute/helper
```

Use the corresponding target directory and `.exe` name on Windows. Build inputs come from the existing runtime receipt and pinned fastjsonschema Git submodule. No package installation or application dependency download occurs inside the helper builder. Its receipt retains every payload digest and original validator grant.

This is a development helper. Authenticated immutable installation/signing, actual VLC, physical media/device acceptance and application provider activation remain separate requirements. The Kotlin transport and Compose UI remain source-only until the Linux compiler/native/font dependency closure and actual GUI acceptance are complete. A portable .NET pipe probe on Linux establishes its OS process/pipe boundary, not a compiled Kotlin application.
