package syncwatch

import kotlinx.coroutines.CoroutineScope
import syncwatch.design.LibraryEntry
import syncwatch.design.LibraryPresentation
import syncwatch.design.LibraryVisualState

internal suspend fun roomPlaybackGateChecks(scope: CoroutineScope) {
    val controller = RoomController(scope)
    val source = LibraryPresentation(state = LibraryVisualState.selected,
        entries = listOf(LibraryEntry("movie", "Movie", "Movies/Movie")), selectedID = "movie", enabledActions = setOf("startWatching"))
    check(source.allows("startWatching"))
    for (state in listOf("connecting", "connected", "failed")) {
        controller.editor = controller.editor.copy(state = state)
        check(!controller.libraryPresentation(source).allows("startWatching"))
        if (state == "failed") check(controller.editor.context.values["can.leaveRoom"] == "true")
        controller.close()
        check(controller.libraryPresentation(source).allows("startWatching"))
    }
    println("SYNCWATCH_ROOM_PLAYBACK_GATE_OK explicit exit after failure")
}
