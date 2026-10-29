# Start watching

Start watching prepares the selected native input, restores its saved position and initial local tracks, then begins playback. Local starts use the same scoped preparation and autoplay path as playlist selections.

In a room, the client that successfully commits a new watch generation submits one seek-and-play intent after authenticated Syncplay admission. A client joining an already active generation accepts the room's current timing and paused state. Losing a concurrent selection does not authorize Play for the winning generation.

The room coordinator retains this decision within its existing owned transition task. Failed preparation, missing media, cancellation, End and Close cannot submit the initial Play. Reconnecting an admitted input does not repeat Start. All playback observations remain authoritative; the interface does not optimistically display Playing.

Swift/macOS, C#/Windows and Kotlin/Linux apply the same lifecycle. Common Design owns the existing action and presentation; native coordinators own preparation and transport admission.
