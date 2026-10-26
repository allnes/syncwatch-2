package syncwatch.bridge

import java.nio.file.Path
import java.util.concurrent.CompletableFuture
import java.util.concurrent.Executors
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import syncwatch.domain.*
import syncwatch.ipc.Json

private const val SESSION_REVISION = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

/** Scripted IPC peer with a user-write gate; it does not decide playback timing. */
private class SessionPeer : HelperTransport {
    private var context = emptyMap<String, Any?>()
    private val incoming = ArrayDeque<ByteArray>()
    private val sent = mutableListOf<Map<String, Any?>>()
    private var reading: CompletableFuture<ByteArray>? = null
    private var writing: CompletableFuture<Unit>? = null
    private var event = 0L
    private var ended = false
    private var holdUser = false
    @Volatile var userWriteHeld = false
        private set
    private fun base(kind: String, payload: Map<String, Any?>): MutableMap<String, Any?> = mutableMapOf(
        "v" to 1L, "type" to kind, "payload" to payload, "clientRunId" to context["clientRunId"],
        "mediaGeneration" to context["mediaGeneration"])
    private fun push(value: Map<String, Any?>) {
        val data = (Json.write(value) + "\n").toByteArray(Charsets.UTF_8)
        val current = reading; reading = null
        if (current != null) current.complete(data) else incoming.addLast(data)
    }
    private fun emit(kind: String, payload: Map<String, Any?>) {
        push(base(kind, payload).also { it["id"] = "event-${++event}" })
    }
    @Synchronized override fun send(frame: ByteArray): CompletableFuture<Unit> {
        val value = PlayerCorrection.frameValue(frame); context = value
        if (value["origin"] == "user" && holdUser) {
            userWriteHeld = true
            return CompletableFuture<Unit>().also { writing = it }.thenApply { finish(value) }
        }
        finish(value); return CompletableFuture.completedFuture(Unit)
    }
    @Synchronized private fun finish(value: Map<String, Any?>) {
        check(!ended); sent.add(value)
        val id = value["id"] ?: return
        val kind = value["type"]
        if (kind == "player.state") return
        val hello = kind == "bridge.hello"
        push(base(if (hello) "bridge.ready" else "bridge.result",
            if (hello) mapOf("syncplayRevision" to SESSION_REVISION) else mapOf("status" to "applied")).also { it["replyTo"] = id })
        if (kind == "sync.connect") {
            emit("sync.identity", mapOf("username" to "Viewer_2")); emit("sync.connection", mapOf("state" to "connected"))
        }
        if (kind == "sync.setReady") emit("sync.readiness", mapOf("ready" to true))
    }
    @Synchronized override fun read(): CompletableFuture<ByteArray> {
        if (incoming.isNotEmpty()) return CompletableFuture.completedFuture(incoming.removeFirst())
        if (ended) return CompletableFuture.failedFuture(IllegalStateException("EOF"))
        return CompletableFuture<ByteArray>().also { reading = it }
    }
    @Synchronized override fun close() {
        ended = true; reading?.completeExceptionally(IllegalStateException("EOF")); reading = null
        writing?.completeExceptionally(IllegalStateException("EOF")); writing = null
    }
    @Synchronized fun readiness(value: Boolean) { emit("sync.readiness", mapOf("ready" to value)) }
    @Synchronized fun gateUserWrite() { holdUser = true }
    @Synchronized fun releaseUserWrite() { holdUser = false; val current = writing; writing = null; current?.complete(Unit) }
    @Synchronized fun correction(id: Long, after: Long, position: Long) {
        push(base("player.setPosition", mapOf("positionMs" to position)).also { it["id"] = "cmd-$id"; it["afterUserAction"] = after })
    }
    @Synchronized fun replyCount(id: Long, kind: String) = sent.count { it["replyTo"] == "cmd-$id" && it["type"] == kind }
    @Synchronized fun userCount() = sent.count { it["origin"] == "user" }
}

private class SessionPlayer(private val scope: PlaybackScope) : PlaybackPort {
    private var sequence = 0uL
    @Volatile var paused = false
        private set
    var position = 1200L
        private set
    var seeks = 0
        private set
    var closes = 0
        private set
    override suspend fun observe(scope: PlaybackScope): PlaybackObservation {
        this.scope.check(scope)
        return PlaybackObservation(scope, ++sequence, PlaybackStatus.ready, position, 60000, paused, 1.0,
            true, false, false, 0, 0, 0, null, false)
    }
    override suspend fun setPaused(paused: Boolean, scope: PlaybackScope) { this.paused = paused }
    override suspend fun seek(positionMs: Long, scope: PlaybackScope) { position = positionMs; seeks++ }
    override suspend fun load(localFile: Path, scope: PlaybackScope): Unit = error("Unexpected load")
    override suspend fun setRate(rate: Double, scope: PlaybackScope): Unit = error("Unexpected rate")
    override suspend fun setVolume(volume: Double, muted: Boolean, scope: PlaybackScope): Unit = error("Unexpected volume")
    override suspend fun tracks(subtitles: Boolean, scope: PlaybackScope): List<PlaybackTrack> = emptyList()
    override suspend fun selectTrack(id: Int, subtitles: Boolean, scope: PlaybackScope): Unit = error("Unexpected track")
    override suspend fun stop(scope: PlaybackScope): Unit = error("Unexpected stop")
    override suspend fun close() { closes++ }
}

private suspend fun eventually(predicate: () -> Boolean) {
    val end = System.nanoTime() + 3_000_000_000
    while (!predicate()) { check(System.nanoTime() < end) { "Session check timeout" }; delay(10) }
}

private suspend fun scenario(owner: CoroutineScope, eof: Boolean, strict: Boolean = false) {
    val native = PlaybackScope.fresh().replacingMedia(); val player = SessionPlayer(native); val peer = SessionPeer()
    val session = HelperSession(peer, player, native, SyncplayEndpoint("localhost", 8999, "room", "Viewer"),
        SharedMedia("media-1", "Movie.mkv", 60000, 1234), SESSION_REVISION, owner, requireDeclaredIdentity = strict)
    try {
        if (strict) {
            player.setPaused(false, native)
            session.start(); eventually { session.state.connection == HelperConnection.failed }
            check(!session.state.ready && session.state.identityRejected && session.state.acceptedUsername == null && peer.userCount() == 0)
            return
        }
        session.start(); eventually { session.state.ready }
        check(session.state.acceptedUsername == "Viewer_2" && player.paused && peer.userCount() == 0)
        if (eof) {
            session.pause(false); eventually { peer.userCount() == 1 }
            peer.close(); eventually { session.state.connection == HelperConnection.failed }
        } else {
            peer.gateUserWrite(); session.pause(false); eventually { peer.userWriteHeld }
            peer.correction(1, 1, 2400); delay(30)
            check(session.state.connection == HelperConnection.connected && player.seeks == 0)
            peer.releaseUserWrite(); eventually { peer.replyCount(1, "player.result") == 1 }
            peer.correction(1, 1, 2400); eventually { peer.replyCount(1, "player.result") == 2 }
            check(player.seeks == 1)
            peer.readiness(false); eventually { !session.state.ready }
            session.seek(3000); eventually { peer.userCount() == 2 }
            peer.correction(2, 0, 0); eventually { peer.replyCount(2, "bridge.error") == 1 }
            check(player.position == 3000L && peer.userCount() == 2)
            peer.correction(3, 3, 0); eventually { session.state.connection == HelperConnection.failed }
        }
    } finally { session.close(); session.close(); check(player.paused && player.closes == 0) }
    check(player.paused && player.closes == 0)
}

internal fun helperSessionChecks() {
    Executors.newSingleThreadExecutor().asCoroutineDispatcher().use { dispatcher ->
        runBlocking(dispatcher) { scenario(this, false); scenario(this, true); scenario(this, false, strict = true) }
    }
    println("SYNCWATCH_HELPER_SESSION_OK publication race replay stale correction future authority EOF cleanup")
}
