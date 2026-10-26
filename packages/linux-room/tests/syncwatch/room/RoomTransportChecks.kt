package syncwatch.room

import java.util.UUID
import kotlinx.coroutines.*

suspend fun transportChecks() {
    val address = System.getenv("SYNCWATCH_ROOM_SERVICE") ?: return
    val key = System.getenv("SYNCWATCH_ROOM_CREATION_KEY") ?: return
    val owner = RoomClient(RoomAddress(address)); val guest = RoomClient(RoomAddress(address))
    try {
        withTimeout(30000) {
            val admission = owner.create(RoomIdentity("run-" + UUID.randomUUID().toString(), "Linux owner"),
                RoomConnection("syncplay.example.com", 8999, "Room check"), RoomSecret(key))
            val events = owner.openEvents(admission)
            val initial = RoomBootstrap.initialEvent(events.receive(), admission)
            check(initial.snapshot.members.size == 1)
            val empty = owner.catalog(admission, initial, initial.catalogCursor)
            check(empty.items.isEmpty() && empty.nextCursor == null)
            val refreshed = owner.snapshot(admission)
            check((runCatching { owner.catalog(admission, initial, initial.catalogCursor) }.exceptionOrNull() as? RoomProtocolException)?.code == "snapshotRequired")
            owner.catalog(admission, refreshed, refreshed.catalogCursor)
            val joined = guest.join(admission.roomId, admission.invitation!!, RoomIdentity("run-" + UUID.randomUUID().toString(), "Linux guest"))
            val guestEvents = guest.openEvents(joined)
            check(RoomBootstrap.initialEvent(guestEvents.receive(), joined).snapshot.members.size == 2)
            check(RoomWire.parse(events.receive())["type"] == "member.bound")
            check(owner.snapshot(admission).snapshot.members.size == 2)
            guest.leave(joined)
            check(RoomWire.parse(events.receive())["type"] == "member.left")
            owner.leave(admission); owner.close(); owner.close()
            check(runCatching { owner.snapshot(admission) }.exceptionOrNull() is RoomProtocolException)
        }
        println("SYNCWATCH_ROOM_TRANSPORT_OK")
        seededCatalog(address)
        commandTransportChecks(address, key)
    } finally { guest.close(); owner.close() }
}

private suspend fun seededCatalog(address: String) {
    val room = System.getenv("SYNCWATCH_CATALOG_ROOM") ?: return
    val invitation = System.getenv("SYNCWATCH_CATALOG_INVITATION") ?: return
    val client = RoomClient(RoomAddress(address))
    try {
        withTimeout(20000) {
            val admission = client.join(room, RoomSecret(invitation), RoomIdentity("run-" + UUID.randomUUID().toString(), "Linux catalog"))
            val events = client.openEvents(admission)
            val bootstrap = RoomBootstrap.initialEvent(events.receive(), admission)
            var cursor: String? = bootstrap.catalogCursor
            val ids = mutableSetOf<String>(); var pages = 0
            while (cursor != null) {
                val page = client.catalog(admission, bootstrap, cursor)
                for (entry in page.items) check(entry.memberId != admission.memberId && ids.add(entry.media.mediaId))
                check(++pages <= 3)
                cursor = page.nextCursor
            }
            check(pages == 3 && ids == (0 until 250).map { "movie-$it" }.toSet())
            client.leave(admission)
        }
        println("SYNCWATCH_ROOM_CATALOG_TRANSPORT_OK")
    } finally { client.close() }
}
