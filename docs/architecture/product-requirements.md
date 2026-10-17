# Product requirements

SyncWatch is a standalone desktop product for synchronized viewing of local movies. The first release targets macOS and Windows 11 x64. Each participant plays a local media file; movie content is not relayed through the synchronization or metadata services.

Requirement IDs are shared by implementation, contract fixtures, and release acceptance. A requirement is complete only when its behavior has been verified on both clients. An unresolved integration capability remains an unmet requirement.

## Functional requirements

| ID | Required behavior | Owner | Acceptance criteria |
|---|---|---|---|
| F01 | Select a local movie folder, scan subfolders, search, rescan, and refresh automatically when enabled | LibraryService | Folder changes and filesystem updates produce a consistent catalog; unavailable folders have a recoverable error state |
| F02 | Discover MKV, MP4, AVI, MOV, M4V, WEBM, WMV, MPG, MPEG, TS, and M2TS files | LibraryService / MediaProbe | Discovery handles every listed extension; playback reports actual codec support rather than relying on the extension |
| F03 | Display duration, resolution, audio tracks, and subtitle tracks | MediaProbe | Metadata comes from the media engine; unavailable metadata is shown explicitly |
| F04 | Associate external audio and subtitle files with movies and support movie folders | LibraryIndex | Matching handles names with multiple dots, nested folders, deterministic ordering, and filesystem case rules |
| F05 | Match movies across participants without sharing absolute local paths | MediaIdentity / RoomMetadata | Normalized names identify candidates; content identity and edition checks prevent an ambiguous automatic match |
| F06 | Show room connectivity, participant presence, readiness, and recent activity | SyncPort / RoomPort | Presence and playback synchronization are independent of call state |
| F07 | Start, continue, and end a watch session; return to the library while retaining active playback | WatchSessionCoordinator | Returning home retains the active session; ending releases it; restarting the app does not silently reactivate an old session |
| F08 | Synchronize play, pause, seek, media start, and session end | SyncplayBridge / WatchSessionCoordinator | Either participant can act; stale commands and commands for a different session cannot change current playback |
| F09 | Coordinate readiness and handle missing media | SyncPort / RoomPort | Playback waits for valid media and readiness; missing or incompatible files produce an actionable state |
| F10 | Show timeline frame previews with a bounded cache | PreviewService | Preview decoding never seeks the main player, sends a playback command, or captures a stale frame after cancellation |
| F11 | Show a playlist and support previous/next media selection | WatchSessionCoordinator | Participants agree on the active media generation before playback begins |
| F12 | Select embedded or external audio and subtitles | PlaybackPort | Track choices refer to actual available tracks; external assets remain local |
| F13 | Control movie volume/mute, default volume, remembered volume, and independent call volume | LocalAudioPolicy / CallPort | Only the intended media output changes; independent Meet volume remains subject to the call capability gate |
| F14 | Optionally reduce movie volume while a remote participant speaks | LocalAudioPolicy / CallPort | Apply a 0.35 movie-volume multiplier with a 280 ms release delay; restore the user volume afterward. A reliable remote-speaking signal is required |
| F15 | Provide keyboard playback controls | Platform input adapter | Left/right skip, Space toggles playback, up/down changes movie volume by 5%, M mutes, F toggles fullscreen, and Escape exits fullscreen; editable fields and call input retain their keys |
| F16 | Provide fullscreen, cursor/control auto-hide, context menus, popovers, and volume feedback | PlayerChrome / window manager | Controls remain visible, focusable, and clickable across resize, display-scale changes, and fullscreen transitions |
| F17 | Support dark, light, and system themes, plus English and Russian UI localization | Design renderer / SettingsService | Theme and language changes apply without restart; text fits the supported layouts |
| F18 | Provide library, interface, call, and connection settings | SettingsService / SettingsDialog | Changes persist with clear saved-state feedback and validation errors |
| F19 | Configure skip interval, previews, and subtitle size, font, colors, outline, padding, and position | SettingsService / PlayerCapabilities | Each enabled setting has a working runtime mapping and a section reset action |
| F20 | Configure brightness, contrast, saturation, hue, audio normalization, scaling, fullscreen cursor behavior, and preview cache budget | PlaybackPort / PreviewService | Settings visibly affect the intended output; preview cache is configurable from 50 to 500 MB |
| F21 | Host a call in a separate application-owned window with move, resize, pin, minimize, restore, and fullscreen controls | CallWindowShell / CallPort | Camera, microphone, device selection, hangup, and capture shutdown pass the Meet integration gate |
| F22 | Configure call input/output devices and supported camera quality | CallPort | Expose only functioning capabilities; 480p is a quality target whose availability must be verified |
| F23 | Handle interruptions and participant reconnection | ConnectionSupervisor | Synchronization loss pauses playback; call-only failure does not stop the movie; reconnect does not replay obsolete actions |
| F24 | Retain authorized access to a selected movie folder across restarts | Platform library access adapter | macOS security-scoped bookmarks handle moved, stale, denied, and corrupt grants; loading preferences remains recoverable |
| F25 | Release media, previews, permissions, and helper processes predictably | Lifecycle owners | End, close, cancellation, and crash recovery leave no orphan helper or hidden camera/microphone capture |

F13, F14, F21, and F22 depend on unverified Google Meet host capabilities. F10, F12, F19, and F20 require validation against the selected VLC configuration. Keeping a disabled or ineffective control does not satisfy a requirement.

## Visual requirements

The source of truth is the platform-neutral design package in `packages/design/`. Native clients must implement its component structures, states, and actions using the same token IDs.

| Element | Specification |
|---|---|
| Dark surfaces | Background `#071827`, deep background `#05121E`, surface `#0C2135`, raised surface `#102A43`, border `#1B4060` |
| Light surfaces | Background `#E7EEF4`, deep background `#DCE6EE`, surface `#F1F5F8`, raised surface `#F7FAFC`, border `#B9C9D6` |
| Accent and success | Accent `#2F8CFF`, soft accent `#6AAFFF`, success `#30D98B` |
| Library layout | Outer padding 18, panel gap 14, header height 64, left column width 360 |
| Settings dialog | 680 by 420, sidebar width 150 |
| Player settings dialog | 680 by 460, sidebar width 170, draggable title bar |
| Buttons and slider | Filled button minimum height 46, outlined minimum height 44, button radius 12, slider track height 3, thumb radius 6 |
| Call window shell | Initial size token 300 by 210; the usable Meet viewport must pass acceptance before the final minimum size is approved |

Dimensions use logical points on macOS and device-independent pixels on Windows. Typography, icon shapes, focus behavior, and responsive layouts require visual acceptance in addition to token equality.

## Product boundaries

Local movie files remain on the participant's device. Synchronization, metadata, and calling have separate connection states. Preferences and authorized filesystem access persist locally. Shared design data contains no account, device, room, or meeting information.

All project documentation is written in English. Product UI localization is a separate concern.
