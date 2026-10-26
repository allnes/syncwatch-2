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
            check(RoomBootstrap.initialEvent(events.receive(), admission).snapshot.members.size == 1)
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
    } finally { guest.close(); owner.close() }
}
