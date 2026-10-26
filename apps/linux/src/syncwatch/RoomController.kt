package syncwatch

import androidx.compose.runtime.*
import kotlinx.coroutines.*
import syncwatch.design.RoomEditor
import syncwatch.room.*

/** The workspace owns membership independently of the visible dialog. */
internal class RoomController(private val scope: CoroutineScope) {
    var editor by mutableStateOf(RoomEditor())
    var bootstrap by mutableStateOf<RoomBootstrap?>(null)
        private set
    val connected: Boolean get() = editor.connected && bootstrap != null
    private var admission: RoomAdmission? = null
    private var work: Job? = null
    private var stopping = false
    private var closing: CompletableDeferred<Unit>? = null
    fun connect() {
        if (stopping || editor.busy || connected || work != null || !editor.isValid) return
        val values = editor.values; val owner = editor.mode == "createRoom"
        editor = editor.copy(state = "connecting", status = "")
        val job = scope.launch(start = CoroutineStart.LAZY) { run(values, owner) }; work = job; job.start()
    }
    fun libraryPresentation(source: syncwatch.design.LibraryPresentation) = source.copy(
        enabledActions = (source.enabledActions + if (stopping) emptySet() else setOf("openRoom")) -
            if (editor.state != "disconnected") setOf("startWatching") else emptySet(),
        roomStatus = if (connected) "roomMetadataConnected" else if (editor.busy) "roomConnecting" else if (editor.state == "failed") "roomConnectionFailed" else "disconnected")
    fun pasteInvitation(text: String) {
        if (stopping || editor.busy || editor.connected || editor.mode != "joinRoom") return
        editor = try {
            val invitation = RoomInvitation.parse(text)
            editor.edit("roomID", invitation.roomId).edit("invitation", invitation.credential.copyInvitation())
        } catch (_: RoomProtocolException) {
            editor.clearSecrets().edit("roomID", "").copy(status = "roomInvitationInvalid")
        }
    }
    fun invitationToCopy(): String? = if (connected) admission?.let { value -> value.invitation?.let { RoomInvitation(value.roomId, it).copyText() } } else null
    fun invitationCopied() { editor = editor.copy(status = "roomInvitationCopied") }
    suspend fun close() = withContext(NonCancellable) {
        closing?.let { it.await(); return@withContext }
        val completion = CompletableDeferred<Unit>(); closing = completion
        stopping = true
        work?.cancelAndJoin()
        work = null; admission = null; bootstrap = null
        editor = editor.clearSecrets().copy(state = "disconnected", status = "", roomId = "", memberCount = 0, owner = false)
        stopping = false; completion.complete(Unit); closing = null
    }
    private suspend fun run(values: Map<String, String>, owner: Boolean) {
        var current: RoomClient? = null; var admitted: RoomAdmission? = null
        var failed = false
        try {
            val next = RoomClient(RoomAddress(values.getValue("serviceAddress"))); current = next;
            val identity = RoomIdentity("run-" + java.util.UUID.randomUUID().toString(), values.getValue("username"))
            val value = if (owner) next.create(identity, RoomConnection(values.getValue("syncplayHost"), values.getValue("syncplayPort").toInt(), values.getValue("roomName")), RoomSecret.fromInput(values.getValue("creationKey")))
                else next.join(values.getValue("roomID"), RoomSecret.fromInput(values.getValue("invitation")), identity)
            admitted = value; admission = value; editor = editor.clearSecrets()
            val stream = next.openEvents(value)
            val initial = withTimeout(20000) { RoomBootstrap.initialEvent(stream.receive(), value) }
            currentCoroutineContext().ensureActive(); bootstrap = initial
            editor = editor.copy(state = "connected", roomId = value.roomId, memberCount = initial.snapshot.members.size, owner = owner)
            while (currentCoroutineContext().isActive) {
                val update = RoomInvalidation.decode(stream.receive()); val previous = bootstrap ?: throw RoomProtocolException("malformed")
                if (update.epoch != previous.snapshot.epoch) throw RoomProtocolException("malformed")
                if (update.sequence <= previous.snapshot.sequence) continue
                val snapshot = next.snapshot(value)
                if (snapshot.snapshot.epoch != previous.snapshot.epoch || snapshot.snapshot.sequence < update.sequence || snapshot.connection.host != initial.connection.host ||
                    snapshot.connection.port != initial.connection.port || snapshot.connection.room != initial.connection.room ||
                    snapshot.snapshot.members.none { it.memberId == value.memberId && it.identity == identity }) throw RoomProtocolException("malformed")
                bootstrap = snapshot; editor = editor.copy(memberCount = snapshot.snapshot.members.size)
            }
        } catch (error: CancellationException) { throw error }
        catch (_: Exception) { failed = true; editor = editor.copy(state = "connecting") }
        finally {
            withContext(NonCancellable) {
                current?.let { target -> admitted?.let { value -> withTimeoutOrNull(3000) { runCatching { target.leave(value) } } }; target.close() }
                admission = null; bootstrap = null; editor = editor.clearSecrets().copy(memberCount = 0, owner = false); work = null
                if (failed) editor = editor.copy(state = "failed", status = "roomConnectionFailed")
            }
        }
    }
}
