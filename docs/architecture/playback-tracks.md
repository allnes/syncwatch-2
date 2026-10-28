# Local playback tracks

Each active movie has one local track controller and one playback owner. The controller depends on `PlaybackTrackControlPort`, correlates menu requests with its source identity and revision, and uses the current movie's playback scope. Audio and subtitle choices never enter room metadata or Syncplay user intents.

Opening a menu reads the engine's track descriptions and selected ID. Selecting a row disables further choices until the engine acknowledges the request; a submitted command does not change the observed selection. Successful selection closes the menu. Reopening reads the current engine state. An unavailable provider produces the common unavailable presentation; closing and reopening retries the read. Requests from a dismissed menu, replaced movie or closed owner cannot publish a result. Teardown cancels and awaits outstanding reads before releasing the native player.

The Apache-2.0 Design library owns menu geometry, localized disabled-track labels, selection markers and button placement. Applications provide observations and correlated events. The common document attaches a popover slot, edge and dismissal action to each track button. Native primitive adapters host that content above the video surface and dismiss it when its retained pane becomes hidden. They do not create another media owner.

Linux Design owns a transient native popup with a Compose panel rendered through Swing graphics above heavyweight video. The shared document supplies its intrinsic content size and placement edge. The host observes anchor geometry, owner movement, outside clicks, Escape and focus loss, and disposes its window, composition and listeners together. It requires no global toolkit-layer setting or application presentation logic.

The native adapter reads selected IDs from VLC. After changing a seekable input's track, it refills the demuxer at the actual local clock: packets for the previously unselected stream may already have been discarded during prebuffering. This preserves pause state and does not submit a shared seek intent.

The media build retains narrowly configured VLC codec aliases for SubRip and ASS streams delivered by avformat. Original pinned sources and grants remain intact in the source archives; the configured file, change notice and exact derivative hashes accompany the SDK. No third-party checkout is edited to apply the configuration.

Verification separates selected IDs from output. Native checks measure the alternate embedded PCM tone and actual rendered SubRip/ASS pixels using authored media, in addition to scope, cancellation and close checks. Interactive qualification exercises the ordinary native controls on macOS, Windows and Linux and verifies that local selections leave peers' tracks unchanged while shared transport continues to work.
