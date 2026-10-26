package syncwatch

import kotlinx.coroutines.CoroutineScope
import syncwatch.design.LibraryEntry
import syncwatch.design.LibraryPresentation
import syncwatch.design.LibraryVisualState

internal suspend fun roomPlaybackGateChecks(scope: CoroutineScope) {
    val controller = RoomController(scope)
    controller.editor = controller.editor.selectMode("joinRoom").edit("serviceAddress", "https://rooms.example.com").edit("username", "Peer")
    val credential = "A".repeat(64)
    controller.pasteInvitation("room-paste\r\n" + credential)
    check(controller.editor.values["roomID"] == "room-paste" && controller.editor.values["invitation"] == credential && controller.editor.isValid)
    check(controller.editor.values["serviceAddress"] == "https://rooms.example.com")
    controller.editor = controller.editor.copy(state = "connecting"); controller.pasteInvitation("invalid")
    check(controller.editor.values["invitation"] == credential)
    controller.editor = controller.editor.copy(state = "disconnected"); controller.pasteInvitation("invalid")
    check(controller.editor.values["roomID"] == "" && controller.editor.values["invitation"] == "" && !controller.editor.isValid)
    check(controller.editor.status == "roomInvitationInvalid" && controller.editor.values["username"] == "Peer")
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
    println("SYNCWATCH_ROOM_INVITATION_OK atomic paste with an explicit service destination")
}
