package syncwatch.room

import java.util.UUID
import kotlinx.coroutines.withTimeout
import syncwatch.domain.MediaDescriptor

suspend fun commandTransportChecks(address: String, key: String) {
    val owner = RoomClient(RoomAddress(address)); val guest = RoomClient(RoomAddress(address))
    try {
        withTimeout(30000) {
            val admission = owner.create(RoomIdentity("run-" + UUID.randomUUID().toString(), "Linux commands"), RoomConnection("syncplay.example.com", 8999, "Commands check"), RoomSecret(key))
            val events = owner.openEvents(admission); RoomBootstrap.initialEvent(events.receive(), admission)
            val catalog = (0 until 250).map { i -> MediaDescriptor("movie-$i", "Movie $i", "movie $i", 1024L + i, 60000, i.toString(16).padStart(64, '0')) }
            for (index in 0 until 3) {
                val command = RoomCommand(admission, index + 1L, 0, RoomCommandAction.Catalog("batch-native", index * 100L, catalog.drop(index * 100).take(100), index == 2))
                val first = owner.execute(admission, command); val replay = owner.execute(admission, command)
                check(first.errorCode == null && first.id == replay.id && first.sequence == replay.sequence && replay.errorCode == null)
                if (index == 0) {
                    val partial = owner.snapshot(admission)
                    check(owner.catalog(admission, partial, partial.catalogCursor).items.isEmpty())
                }
            }
            val view = owner.snapshot(admission); var cursor: String? = view.catalogCursor; val ids = mutableSetOf<String>()
            while (cursor != null) {
                val page = owner.catalog(admission, view, cursor)
                for (item in page.items) check(item.memberId == admission.memberId && ids.add(item.media.mediaId))
                cursor = page.nextCursor
            }
            check(ids == catalog.map { it.mediaId }.toSet())
            val selection = RoomCommand(admission, 4, 0, RoomCommandAction.Select("movie-0"))
            val selected = owner.execute(admission, selection); val replay = owner.execute(admission, selection)
            check(selected.errorCode == null && selected.sequence == replay.sequence && replay.errorCode == null)
            val selectedView = owner.snapshot(admission)
            val definition = owner.selection(admission, selectedView)
            check(definition.selection?.memberId == admission.memberId && definition.selection.media == catalog[0])
            owner.catalogView(admission, selectedView)
            check((runCatching { owner.selection(admission, view) }.exceptionOrNull() as? RoomProtocolException)?.code == "staleGeneration")
            check((runCatching { owner.execute(admission, RoomCommand(admission, 4, 0, RoomCommandAction.Select("movie-1"))) }.exceptionOrNull() as? RoomProtocolException)?.code == "conflict")
            check(owner.execute(admission, RoomCommand(admission, 5, 0, RoomCommandAction.Select("movie-1"))).errorCode == "staleGeneration")
            for (command in listOf(RoomCommand(admission, 6, 1, RoomCommandAction.Start("movie-0")), RoomCommand(admission, 7, 2, RoomCommandAction.Missing("movie-0", true)),
                RoomCommand(admission, 8, 2, RoomCommandAction.End(RoomWatchEndReason.user)), RoomCommand(admission, 9, 3, RoomCommandAction.Meet("https://meet.google.com/abc-defg-hij")),
                RoomCommand(admission, 10, 3, RoomCommandAction.Meet(null)))) check(owner.execute(admission, command).errorCode == null)
            val final = owner.snapshot(admission)
            check(final.snapshot.watchStatus == "ended" && final.snapshot.watchGeneration == 3L && final.snapshot.meetUri == null && admission.memberId in final.missingMembers)
            val joined = guest.join(admission.roomId, admission.invitation!!, RoomIdentity("run-" + UUID.randomUUID().toString(), "Linux command guest"))
            val guestEvents = guest.openEvents(joined); RoomBootstrap.initialEvent(guestEvents.receive(), joined)
            check(guest.execute(joined, RoomCommand(joined, 1, 3, RoomCommandAction.Meet(null))).errorCode == "forbidden")
            check((runCatching { guest.execute(joined, selection) }.exceptionOrNull() as? RoomProtocolException)?.code == "malformed")
            guest.leave(joined); owner.leave(admission)
        }
        println("SYNCWATCH_ROOM_COMMAND_TRANSPORT_OK")
    } finally { guest.close(); owner.close() }
}
