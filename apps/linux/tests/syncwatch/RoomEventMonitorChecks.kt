package syncwatch

import java.util.UUID
import kotlinx.coroutines.*
import syncwatch.domain.MediaDescriptor
import syncwatch.room.*

internal suspend fun roomEventMonitorChecks(address: String, key: String) = coroutineScope {
    val client = RoomClient(RoomAddress(address))
    var monitoring: Job? = null
    try {
        val identity = RoomIdentity("run-" + UUID.randomUUID(), "Linux recovery")
        val admission = client.create(identity, RoomConnection("syncplay.example.com", 8999, "Recovery"), RoomSecret(key))
        val owner = RoomMembershipSession(client, admission, identity)
        val media = MediaDescriptor("movie", "Movie", "movie", 10, 60000, null)
        owner.publish(listOf(media))
        var deliveries = 0; var recoveries = 0
        monitoring = launch {
            RoomEventMonitor.run(RoomAddress(address), admission, owner, reconnecting = { recoveries++ }, accepted = { view ->
                check(view.bootstrap.snapshot.members.any { it.memberId == admission.memberId && it.identity == identity })
                deliveries++; if (deliveries == 1) throw RoomProtocolException("transport")
            })
        }
        withTimeout(10000) { while (deliveries < 2) delay(10) }
        check(recoveries == 1)
        owner.publish(listOf(media))
        val selected = owner.perform(RoomCommandAction.Select(media.mediaId), owner.watchContext())
        check(selected.definition.selection?.media == media)
        monitoring.cancelAndJoin(); monitoring = null
        var retries = 0
        val failure = runCatching {
            RoomEventMonitor.run(RoomAddress(address), admission, owner, reconnecting = { retries++ },
                accepted = { throw RoomProtocolException("malformed") })
        }.exceptionOrNull()
        check(failure is RoomProtocolException && failure.code == "malformed" && retries == 0)
        client.leave(admission)
        println("SYNCWATCH_ROOM_EVENT_RECOVERY_OK retained identity/commands, terminal metadata, cancel/join")
    } finally {
        withContext(NonCancellable) { monitoring?.cancelAndJoin(); client.close() }
    }
}
