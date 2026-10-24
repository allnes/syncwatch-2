# Desktop application acceptance

Each feature is implemented and checked together on macOS, Windows and Linux.
Run the actual native application in a visible desktop session on each target.
Check its input, focus, window sizing, shared design, unavailable states and
resource release. Build and offscreen rendering results are separate evidence.

Synchronization uses an authenticated Syncplay room. Three clients require six
directed sender/observer cases, even when they share the same room concurrently:

| Sender | Observer |
|---|---|
| macOS | Windows |
| Windows | macOS |
| macOS | Linux |
| Linux | macOS |
| Windows | Linux |
| Linux | Windows |

For each direction, initiate play, pause and seek through the sender's visible
controls. Observe the receiver's real VLC state, position and native output;
compare positions with the synchronization contract's tolerance. A requested
state or transport acknowledgement is insufficient. Check late join, reconnect,
media mismatch, stale generations and closing a participating window. Keep local
volume and track changes local, and check that observations do not echo remote
commands as new user actions.

Record each case against the exact source, dependency and artifact identities,
with its desktop observation and result. A missing client implementation, failed
case or missing receiver observation leaves the feature incomplete. Preserve
failures alongside corrected results. CI exercises the common contracts and
available automated native checks; it does not imply this desktop acceptance.
