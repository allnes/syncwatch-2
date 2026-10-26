package syncwatch

import androidx.compose.runtime.*
import kotlinx.coroutines.*
import syncwatch.design.RoomEditor
import syncwatch.room.*
import syncwatch.library.LocalMediaFile

/** The workspace owns membership independently of the visible dialog. */
internal class RoomController(private val scope: CoroutineScope) {
    var editor by mutableStateOf(RoomEditor())
    var catalogView by mutableStateOf<RoomCatalogView?>(null)
        private set
    val bootstrap: RoomBootstrap? get() = catalogView?.bootstrap
    val connected: Boolean get() = editor.connected && bootstrap != null
    private var admission: RoomAdmission? = null
    private var work: Job? = null
    private var session: RoomMembershipSession? = null
    private var catalogMap = RoomLocalCatalog()
    private var localRevision: java.util.UUID? = null
    private var acknowledgedRevision: java.util.UUID? = null
    private var localFiles: List<LocalMediaFile> = emptyList()
    private var publisher: Job? = null
    private var stopping = false
    private var closing: CompletableDeferred<Unit>? = null
    private fun verifyOwner() { check(java.awt.EventQueue.isDispatchThread()) { "room-event-thread" } }
    fun connect() {
        verifyOwner()
        if (stopping || editor.busy || connected || work != null || !editor.isValid) return
        val values = editor.values; val owner = editor.mode == "createRoom"
        editor = editor.copy(state = "connecting", status = "")
        val job = scope.launch(start = CoroutineStart.LAZY) { run(values, owner) }; work = job; job.start()
    }
    fun libraryPresentation(source: syncwatch.design.LibraryPresentation) = source.copy(
        enabledActions = (source.enabledActions + if (stopping) emptySet() else setOf("openRoom")) -
            if (editor.state != "disconnected") setOf("startWatching") else emptySet(),
        roomStatus = if (connected) (editor.status.takeIf { it in setOf("roomCatalogPublishing", "roomCatalogPublishFailed") } ?: "roomMetadataConnected") else if (editor.busy) "roomConnecting" else if (editor.state == "failed") "roomConnectionFailed" else "disconnected")
    fun pasteInvitation(text: String) {
        verifyOwner()
        if (stopping || editor.busy || editor.connected || editor.mode != "joinRoom") return
        editor = try {
            val invitation = RoomInvitation.parse(text)
            editor.edit("roomID", invitation.roomId).edit("invitation", invitation.credential.copyInvitation())
        } catch (_: RoomProtocolException) {
            editor.clearSecrets().edit("roomID", "").copy(status = "roomInvitationInvalid")
        }
    }
    fun invitationToCopy(): String? = if (connected) admission?.let { value -> value.invitation?.let { RoomInvitation(value.roomId, it).copyText() } } else null
    fun invitationCopyCompleted(copied: Boolean) {
        verifyOwner()
        if (connected) editor = editor.copy(status = if (copied) "roomInvitationCopied" else "roomInvitationCopyFailed")
    }
    suspend fun close() = withContext(NonCancellable) {
        verifyOwner()
        closing?.let { it.await(); return@withContext }
        val completion = CompletableDeferred<Unit>(); closing = completion
        stopping = true
        work?.cancelAndJoin()
        work = null; admission = null; catalogView = null
        editor = editor.clearSecrets().copy(state = "disconnected", status = "", roomId = "", memberCount = 0, owner = false)
        stopping = false; completion.complete(Unit); closing = null
    }
    fun updateLibrary(revision: java.util.UUID, files: List<LocalMediaFile>) {
        verifyOwner()
        if (localRevision == revision) return
        localRevision = revision; localFiles = files.toList(); startPublisher()
    }
    private fun startPublisher() {
        val owner = session ?: return
        if (stopping || !connected || publisher != null || localRevision == null || localRevision == acknowledgedRevision) return
        val task = scope.launch(start = CoroutineStart.LAZY) { publishLibrary(owner) }; publisher = task; task.start()
    }
    private suspend fun publishLibrary(owner: RoomMembershipSession) {
        try {
            while (currentCoroutineContext().isActive && !stopping && session === owner) {
                val revision = localRevision ?: return
                if (revision == acknowledgedRevision) return
                try {
                    val publication = catalogMap.prepare(localFiles)
                    editor = editor.copy(status = "roomCatalogPublishing")
                    val view = owner.publish(publication.items)
                    currentCoroutineContext().ensureActive(); if (stopping || session !== owner) return
                    catalogMap.acknowledge(publication); acknowledgedRevision = revision; accept(view)
                    if (editor.status in setOf("roomCatalogPublishing", "roomCatalogPublishFailed")) editor = editor.copy(status = "")
                } catch (_: Exception) {
                    currentCoroutineContext().ensureActive()
                    if (stopping || session !== owner) return
                    if (localRevision != revision) continue
                    editor = editor.copy(status = "roomCatalogPublishFailed"); return
                }
            }
        } finally { publisher = null }
    }
    private fun accept(view: RoomCatalogView) {
        if (view.bootstrap.snapshot.sequence < (bootstrap?.snapshot?.sequence ?: 0)) return
        catalogView = view; editor = editor.copy(memberCount = view.bootstrap.snapshot.members.size)
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
            val ownerSession = RoomMembershipSession(next, value, identity)
            val firstView = ownerSession.refresh(initial)
            currentCoroutineContext().ensureActive(); session = ownerSession; catalogMap = RoomLocalCatalog(); acknowledgedRevision = null; catalogView = firstView
            editor = editor.copy(state = "connected", roomId = value.roomId, memberCount = initial.snapshot.members.size, owner = owner)
            startPublisher()
            while (currentCoroutineContext().isActive) {
                val update = RoomInvalidation.decode(stream.receive()); val previous = bootstrap ?: throw RoomProtocolException("malformed")
                if (update.epoch != previous.snapshot.epoch) throw RoomProtocolException("malformed")
                if (update.sequence <= previous.snapshot.sequence) continue
                val complete = ownerSession.refresh(sequence = update.sequence)
                currentCoroutineContext().ensureActive(); accept(complete)
            }
        } catch (error: CancellationException) {
            // A bounded receive/page timeout is an attempt failure; owner cancellation still propagates.
            currentCoroutineContext().ensureActive()
            failed = true; editor = editor.copy(state = "connecting")
        }
        catch (_: Exception) { failed = true; editor = editor.copy(state = "connecting") }
        finally {
            withContext(NonCancellable) {
                publisher?.cancelAndJoin(); publisher = null; session = null; acknowledgedRevision = null; catalogMap = RoomLocalCatalog()
                current?.let { target -> admitted?.let { value -> withTimeoutOrNull(3000) { runCatching { target.leave(value) } } }; target.close() }
                admission = null; catalogView = null; editor = editor.clearSecrets().copy(memberCount = 0, owner = false); work = null
                if (failed) editor = editor.copy(state = "failed", status = "roomConnectionFailed")
            }
        }
    }
}
