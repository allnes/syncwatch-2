# Application behavior

This guide describes the intended SyncWatch interface on macOS and Windows, using the [shared component contracts](../packages/design/components.json). The application is under development: Library, appearance settings and isolated component galleries are present; the complete playback/call workflows below still require their adapters.

## Library and watch session

The main window has a header, a text-focused movie-library column, a selected-movie panel, room status, and recent activity. Use shared dark/light resources, logical outer padding 18, panel gap 14, header height 64, and library-column width 360.

Users choose a local movie folder, scan subfolders, search, rescan, and enable automatic refresh. Distinguish empty, scanning, searching, selected-media, inaccessible-folder, and missing-media states. Show available duration, resolution, audio tracks, and subtitles. Match external audio/subtitle files deterministically.

**Start watching**, **Continue watching**, and **End watching** reflect local session state. Returning to the library retains playback; ending releases local player and preview resources. A new application launch may restore a saved position without silently restarting a watch session. Ending locally does not issue an extra peer playback action.

Participants identify the selected movie or playlist item through permitted descriptors and content identity, without sharing absolute file paths or movie bytes. Missing or incompatible media is actionable and never implies readiness.

## Shared playback boundary

Only four user actions change a peer's playback: **play, pause, seek, and select a movie/playlist item**. Skip uses the resulting absolute position, so participants can choose different local skip intervals.

Volume, mute, audio/subtitle selection, subtitle styling, image settings, normalization, scaling, previews, cache budget, window state, fullscreen, cursor visibility, theme, language, and camera/microphone preferences remain local. The call provider transports meeting media independently. Membership, readiness, media identity, authorization, ordering, and timing messages support the protocol; they do not authorize additional synchronized application settings. Internal drift correction is not a shared user playback-speed preference.

## Player and input

The core shared PlayerChrome is implemented in the native component gallery, with matching Compose source. Normal media playback, track/playlist/settings menus, native fullscreen/input policies and video overlays await their integrations.

Preserve the compact top controls, centered skip-back/play-pause/skip-forward controls, timeline, previous/next media, playlist, audio/subtitle menus, settings, library navigation, and call-window focus. Timeline previews use a separately owned decoder and bounded cache; they must not seek the movie, publish playback actions, or display canceled generations.

Fullscreen, minimize, return-to-library, and end-watching remain distinct actions. Popovers, context menus, controls, and previews must render above video and receive input after resize, display-scale changes, and fullscreen transitions.

| Input | Behavior |
|---|---|
| Left / Right | Skip by the local interval and publish the resulting position |
| Space | Toggle play/pause |
| Up / Down | Change movie volume by 5% |
| Mouse wheel | Change movie volume only |
| M | Toggle movie mute |
| F | Toggle fullscreen |
| Escape | Exit fullscreen |

Editable fields and call input retain their keys. Show transient movie-volume feedback without changing call volume.

While video plays and the pointer is idle over the video area, hide the cursor after the configured inactivity interval. Restore it on pointer movement, when paused, and while menus, controls, or editable overlays need interaction. Apply the behavior in windowed and fullscreen playback, only inside the player area.

## Audio and calling

One audio popover provides independent movie and call output controls. Movie mute, default/remembered movie volume, and mouse-wheel changes affect only movie output. Call volume controls received call audio independently of the movie, microphone, other applications, and peers.

Optional movie ducking is disabled by default. When remote-speaking detection is available, movie volume uses a 0.35 multiplier and returns to the user's level after a 280 ms release delay. System communications attenuation and other applications' volume are unaffected.

Use Google Meet in a separate SyncWatch-owned call window. Preserve move, resize, pin, minimize, restore, fullscreen, device selection, microphone/camera controls, and hangup. Show a compact preview of the local camera alongside the remote presentation. Its visibility and state must reflect the actual local capture state, including disabled/denied camera states.

With camera enabled by user preference and permission granted, joining starts the camera and preview on the first attempt, without an off/on workaround. Permission denial or unavailable hardware produces an explicit state. Minimizing an ongoing call does not end it; hangup or closing the call must stop participation, remote audio, and owned capture.

Outside an active joined call, no remote participant audio is audible. Connecting to a synchronization room does not implicitly join a call or open its audio path. After hangup, close, failed join, or call teardown, received call audio stops even if synchronization and movie playback continue.

The initial call size token is 300 by 210. Final minimum dimensions and native call controls depend on the browser host. Independent output volume, local preview, camera startup, and hangup are not implemented in the current shells; see [Meet integration](architecture/google-meet.md) for host limitations.

## Settings

The application-settings dialog uses the shared 680 by 420 layout and 150-unit sidebar:

| Section | Required behavior |
|---|---|
| Library | Select/retain authorized folder access and configure automatic refresh |
| Interface | English/Russian localization and dark/light/system appearance without restart |
| Call | Input/output devices and supported camera quality; retain the 480p target subject to real provider capability |
| Connection | Synchronization/room connection and readiness behavior with independent channel states |

Theme and language are implemented in the native application-settings dialog and saved through the local state store, with feedback and validation errors. They apply without restart and survive application restart; Cancel discards unsaved edits. Library, call and connection controls remain disabled until their adapters are available. Other supported configuration changes follow the same local-save boundary as their integrations are implemented. macOS folder grants use security-scoped bookmarks; moved, stale, denied, or corrupt grants need renewed folder access.

The player-settings dialog uses the shared 680 by 460 layout, 170-unit sidebar, draggable title bar, and section reset actions:

| Section | Required controls |
|---|---|
| Playback | Local skip interval, preview enablement, and supported playback behavior |
| Subtitles | Font, size, text/outline colors, outline width, padding, position, and vertical offset |
| Image | Brightness, contrast, saturation, and hue |
| Audio | Default/remembered movie volume and normalization |
| Advanced | Scaling, cursor behavior, and preview cache from 50 to 500 MB |

Settings depend on the selected VLC modules and preview-service capabilities. Unsupported configuration is shown as unavailable.

## Recovery and visual consistency

Playback synchronization, room metadata, and calling have independent connection states. Show participant presence/readiness and connecting, connected, reconnecting, interrupted, missing-media, and failed states where applicable. Synchronization loss pauses shared playback; a call-only failure leaves the movie running. Reconnect must not replay obsolete actions or create duplicate players, capture streams, or helpers.

Both native platforms share design token IDs, component order, actions, and state contracts. The interface uses a two-column library, deep blue cinema-focused theme, compact dialogs, centered playback controls, timeline previews, audio popover, status indicators, and separate call window. The [architecture](architecture/README.md), [Syncplay integration](architecture/syncplay.md), and [wire contracts](architecture/contracts.md) describe ownership and ordering.
