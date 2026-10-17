# Product acceptance

SyncWatch acceptance covers the [application workflows](../application.md), requirements F01-F28, and integration gates G1-G5 on macOS and Windows. Source checks, domain tests, native media behavior, and physical call acceptance establish different boundaries.

## Shared playback and local state

Two participants must be able to play, pause, seek, and select a movie/playlist item. Verify that stale or foreign-generation actions cannot affect current playback. Different local skip intervals must still produce the intended shared absolute position.

Change movie/call volume, mute, tracks, subtitle styling, image/audio settings, previews, theme/language, window/fullscreen state, cursor behavior, and camera preferences on one client. The peer must retain its own values. Membership/readiness/timing messages may support the protocol but must not introduce another replicated application preference or remote stop/close command. The [wire contracts](contracts.md) define structure and ownership; adapters also enforce this routing policy.

## Library and native player

- Select, retain, revoke, and recover movie-folder access; cover nested folders, ambiguous identities, missing media, and catalog refresh.
- Exercise Start/Continue/End, return-to-library, playlist selection, embedded/external tracks, and saved positions without silently reactivating a watch on process restart.
- Validate native VLC video, overlays, context menus, keyboard actions, settings, scaling, hardware decoding, and preview isolation on both platforms.
- Hide an idle cursor over playing video in windowed and fullscreen modes; restore it on movement, pause, or interactive controls without changing cursor behavior elsewhere.
- Match shared-design component states, geometry, focus, dark/light themes, English/Russian text, long filenames, and display scales.

## Real call behavior

Use the selected application-owned Google Meet hosts with actual camera, microphone, and received media:

- Confirm a compact actual local-camera preview alongside remote video, including disabled, denied, and unavailable states.
- With camera preference enabled and permission granted, the first join must start the camera and self-view without an off/on workaround. Repeat after reconnect and fresh application startup.
- Sweep call output through zero/mute, intermediate, and full volume. Movie output, microphone capture, system/other-app volume, and the peer's settings must not change.
- Before join and after hangup, window close, failed join, or teardown, verify that remote participant audio is silent and owned capture is released. Room connectivity alone must not open call audio.
- Exercise device changes, pin, minimize/restore, fullscreen, denied permissions, expired meetings, and reconnect. A loaded provider page or synthetic preview is not proof of a joined functioning call.
- Run synchronized local movies on two physical devices during the call. Call-only failure must not stop the movie; synchronization failure pauses shared playback. Repeated lifecycle operations must not leave duplicate or orphan resources.

The [Meet contract](google-meet.md) and [dependency policy](dependencies.md) define unresolved host capabilities and source closure. An ineffective slider, camera toggle workaround, or audible inactive call leaves the corresponding requirement open.

## Release condition

A complete release requires every product requirement and G1-G5 to pass or have an explicitly approved scope decision. Builds must have the correct dependency notices, permissions, package identities, and signing/distribution properties. Successful document validation or a native shell build is not complete application acceptance. Source validation and build entry points are documented in [building and running](../building.md).
