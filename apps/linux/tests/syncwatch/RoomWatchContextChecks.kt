package syncwatch

import java.util.UUID
import syncwatch.domain.MediaDescriptor
import syncwatch.room.*

internal suspend fun roomWatchContextChecks() {
    val address = System.getenv("SYNCWATCH_ROOM_SERVICE") ?: return
    val key = System.getenv("SYNCWATCH_ROOM_CREATION_KEY") ?: return
    val client = RoomClient(RoomAddress(address)); val peer = RoomClient(RoomAddress(address))
    try {
        val identity = RoomIdentity("run-" + UUID.randomUUID(), "Linux watch")
        val admission = client.create(identity, RoomConnection("syncplay.example.com", 8999, "Watch context"), RoomSecret(key))
        RoomBootstrap.initialEvent(client.openEvents(admission).receive(), admission)
        val owner = RoomMembershipSession(client, admission, identity)
        val descriptor = MediaDescriptor("movie-a", "Movie", "movie", 1000, 60000, "a".repeat(64))
        owner.publish(listOf(descriptor))
        val idle = owner.watchContext(); check(idle.definition.selection == null)
        val selected = owner.perform(RoomCommandAction.Select("movie-a"), idle)
        check(selected.definition.selection?.media == descriptor)
        owner.publish(emptyList())
        check(owner.watchContext().definition.selection?.media == descriptor)
        val peerIdentity = RoomIdentity("run-" + UUID.randomUUID(), "Linux peer")
        val joined = peer.join(admission.roomId, checkNotNull(admission.invitation), peerIdentity)
        RoomBootstrap.initialEvent(peer.openEvents(joined).receive(), joined)
        val peerOwner = RoomMembershipSession(peer, joined, peerIdentity)
        peerOwner.publish(listOf(descriptor))
        peerOwner.perform(RoomCommandAction.Select("movie-a"), peerOwner.watchContext())
        check((runCatching { owner.perform(RoomCommandAction.Start("movie-a"), selected) }.exceptionOrNull() as? RoomProtocolException)?.code == "staleGeneration")
        val active = owner.perform(RoomCommandAction.Start("movie-a"), owner.watchContext())
        check(active.bootstrap.snapshot.watchStatus == "active" && active.definition.selection?.memberId == joined.memberId)
        owner.perform(RoomCommandAction.End(RoomWatchEndReason.user), active)
        peer.leave(joined); client.leave(admission)
        println("SYNCWATCH_ROOM_WATCH_CONTEXT_OK")
    } finally { peer.close(); client.close() }
}
