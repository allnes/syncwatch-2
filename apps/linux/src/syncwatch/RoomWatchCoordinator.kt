package syncwatch

import androidx.compose.runtime.*
import java.util.UUID
import kotlinx.coroutines.*
import syncwatch.bridge.*
import syncwatch.design.LibraryPresentation
import syncwatch.domain.*
import syncwatch.room.*

/** Metadata admission and helper lifetime; native playback remains owned by the watch coordinator. */
internal class RoomWatchCoordinator(private val room: RoomController, private val watch: WatchSessionCoordinator,
    private val helper: HelperConfiguration, private val scope: CoroutineScope) {
    private data class ActiveWatch(val membership: RoomWatchMembership, val context: RoomWatchContext, val player: PlaybackController)
    private var active: ActiveWatch? = null
    private var work: Job? = null
    private var seenMembership = false
    private var closing = false
    private var admitted = false
    var busy by mutableStateOf(false)
        private set
    var status by mutableStateOf("")
        private set
    var errorKey by mutableStateOf<String?>(null)
        private set
    fun clearError() { errorKey = null }
    fun libraryPresentation(source: LibraryPresentation): LibraryPresentation {
        val result = room.libraryPresentation(source, !busy && active == null)
        val enabled = result.enabledActions.toMutableSet()
        if (room.connected && !busy && active == null && watch.runtimeAvailable && source.selectedID != null) enabled += "startWatching"
        if (busy || closing) enabled -= "startWatching"
        return result.copy(enabledActions = enabled, roomStatus = status.ifEmpty { result.roomStatus })
    }
    fun membershipChanged() {
        if (!room.connected) { seenMembership = false; return }
        if (seenMembership) return
        seenMembership = true
        if (work == null) watch.player?.let { player ->
            player.requireSharedAdmission(); busy = true
            val task = scope.launch(start = CoroutineStart.LAZY) {
                try { player.revokeShared() }
                finally { busy = false; work = null }
            }
            work = task; task.start()
        }
    }
    fun start(selection: LibraryMediaSelection) {
        check(java.awt.EventQueue.isDispatchThread())
        if (closing || work != null) return
        if (room.editor.state == "disconnected") { watch.start(selection); return }
        if (!room.connected || !watch.runtimeAvailable) return
        busy = true; errorKey = null; status = "sharedWatchPreparing"
        val task = scope.launch(start = CoroutineStart.LAZY) { run(selection) }
        work = task; task.start()
    }
    private suspend fun run(selection: LibraryMediaSelection) {
        var publication: RoomPreparedPublication? = null
        var membership: RoomWatchMembership? = null
        var owned: PlaybackController? = null
        var finished = false; admitted = false
        try {
            val (ticket, intent) = room.beginWatch(); membership = ticket
            val runtime = helper.verify()
            currentCoroutineContext().ensureActive()
            watch.end(); watch.start(selection, requiresSharedAdmission = true)
            val nativeScope = watch.scope
            val deadline = System.nanoTime() + 20_000_000_000L
            while (owned == null) {
                currentCoroutineContext().ensureActive()
                check(room.isCurrent(ticket) && watch.scope == nativeScope && watch.errorKey == null && System.nanoTime() < deadline) { "media-unavailable" }
                watch.player?.takeIf { it.scope == nativeScope && !it.failed }?.let { player ->
                    try {
                        val actual = player.player.observe(nativeScope)
                        if (actual.status == PlaybackStatus.ready && actual.seekable && (actual.durationMs ?: 0) > 0) owned = player
                    } catch (cancelled: CancellationException) { throw cancelled }
                    catch (_: Exception) { /* Loading is bounded by the native owner and the admission deadline. */ }
                }
                if (owned == null) delay(100)
            }
            val player = checkNotNull(owned)
            val local = player.prepareSharedMedia()
            val published = room.publishPrepared(local, ticket); publication = published
            var context = room.watchContext(ticket)
            requireSameGeneration(intent, context)
            if (context.bootstrap.snapshot.watchStatus != "active") {
                context = room.performWatch(RoomCommandAction.Select(published.media.mediaId), ticket, context)
                check(context.definition.selection?.media == published.media) { "selection-changed" }
                context = room.performWatch(RoomCommandAction.Start(published.media.mediaId), ticket, context)
            }
            requireMatch(local, context)
            val current = room.watchContext(ticket)
            requireSameGeneration(context, current); requireMatch(local, current)
            check(watch.player === player && watch.scope == nativeScope) { "media-changed" }
            active = ActiveWatch(ticket, current, player)
            currentCoroutineContext().ensureActive()
            var transport: HelperTransport? = null
            try {
                // Keep ownership even if cancellation wins the dispatch back to the UI thread.
                withContext(Dispatchers.IO) { transport = HelperProcess.start(runtime.executable, runtime.packageDirectory) }
                currentCoroutineContext().ensureActive(); check(authorized()) { "watch-revoked" }
                val connection = current.bootstrap.connection; val remote = checkNotNull(current.definition.selection).media
                player.connectShared(checkNotNull(transport), SyncplayEndpoint(connection.host, connection.port, connection.room, ticket.identity.syncplayUsername),
                    SharedMedia("loaded-" + UUID.randomUUID(), remote.title, checkNotNull(local.durationMs), local.fileSizeBytes),
                    runtime.revision, requireDeclaredIdentity = true, authority = ::authorized)
                transport = null
            } finally { withContext(NonCancellable + Dispatchers.IO) { transport?.close() } }
            val readyDeadline = System.nanoTime() + 20_000_000_000L
            while (true) {
                currentCoroutineContext().ensureActive()
                val actual = player.player.observe(nativeScope)
                if (actual.ended) { finished = true; status = "ended"; break }
                check(authorized() && !player.failed && player.sharedState?.connection !in setOf(HelperConnection.failed, HelperConnection.stopped)) { "watch-revoked" }
                if (player.sharedState?.connection == HelperConnection.connected && player.sharedState?.ready == true) {
                    check(player.sharedState?.acceptedUsername == ticket.identity.syncplayUsername) { "identity-changed" }
                    if (!admitted) { player.admitSharedPlayback(); admitted = true }
                    busy = false; status = "sharedWatchConnected"
                } else check(admitted || System.nanoTime() < readyDeadline) { "helper-timeout" }
                delay(100)
            }
        } catch (_: CancellationException) {
        } catch (_: Exception) { val key = if (owned?.sharedState?.identityRejected == true) "sharedWatchIdentityRejected" else "sharedWatchFailed"; errorKey = key; status = key }
        finally {
            withContext(NonCancellable) {
                val previous = active; active = null; admitted = false
                try {
                    owned?.revokeShared()
                    if (finished && previous != null && room.editor.owner && room.isCurrent(previous.membership)) {
                        try { room.performWatch(RoomCommandAction.End(RoomWatchEndReason.finished), previous.membership, previous.context) }
                        catch (_: Exception) { /* Completion metadata is not a peer playback command. */ }
                    }
                }
                finally {
                    publication?.let { value -> membership?.let { room.clearPrepared(value.lease, it) } }
                    busy = false; work = null
                }
            }
        }
    }
    private fun authorized(): Boolean {
        val value = active ?: return false
        if (closing || watch.player !== value.player || watch.scope != value.player.scope) return false
        // Metadata generations govern future admission; Syncplay owns the admitted native scope.
        if (admitted) return room.canContinuePlayback(value.membership)
        val current = room.watchBootstrap ?: return false
        return room.isCurrent(value.membership) &&
            current.snapshot.epoch == value.context.bootstrap.snapshot.epoch && current.snapshot.watchGeneration == value.context.bootstrap.snapshot.watchGeneration && current.snapshot.watchStatus == "active"
    }
    private suspend fun stop() { work?.cancelAndJoin() }
    suspend fun end() {
        val previous = active; stop()
        if (previous != null && room.editor.owner && room.isCurrent(previous.membership)) {
            try { room.performWatch(RoomCommandAction.End(RoomWatchEndReason.user), previous.membership, previous.context) }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { /* Local End already released its own playback. */ }
        }
        watch.end(); status = ""
    }
    suspend fun leave() {
        stop(); room.close(); watch.player?.revokeShared(releaseAdmission = true)
        status = ""; seenMembership = false
    }
    suspend fun close() = withContext(NonCancellable) { closing = true; stop() }
    companion object {
        fun requireSameGeneration(expected: RoomWatchContext, current: RoomWatchContext) {
            if (expected.bootstrap.snapshot.epoch != current.bootstrap.snapshot.epoch || expected.bootstrap.snapshot.watchGeneration != current.bootstrap.snapshot.watchGeneration) throw RoomProtocolException("staleGeneration")
        }
        fun requireMatch(local: MediaDescriptor, context: RoomWatchContext) {
            val selected = context.definition.selection
            check(context.bootstrap.snapshot.watchStatus == "active" && selected != null && MediaAgreement.resolve(selected.media, listOf(local)).status == MediaAgreementStatus.matched) { "media-mismatch" }
        }
    }
}
