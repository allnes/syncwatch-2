package syncwatch.room

import syncwatch.domain.MediaDescriptor

enum class RoomWatchEndReason { user, finished }
sealed interface RoomCommandAction {
    data class Catalog(val batchId: String, val offset: Long, val items: List<MediaDescriptor>, val final: Boolean) : RoomCommandAction
    data class Select(val mediaId: String) : RoomCommandAction
    data class Start(val mediaId: String) : RoomCommandAction
    data class End(val reason: RoomWatchEndReason) : RoomCommandAction
    data class Missing(val mediaId: String, val missing: Boolean) : RoomCommandAction
    data class Meet(val uri: String?) : RoomCommandAction
}

/** Retain until the result is known; retries reuse the original bytes.
 * The application owns monotonically increasing numbers for the membership. */
class RoomCommand(admission: RoomAdmission, number: Long, watchGeneration: Long, action: RoomCommandAction) {
    val id: String
    private val wire: ByteArray
    val encodedBytes: ByteArray get() = wire.copyOf()
    private val roomId = admission.roomId
    private val memberId = admission.memberId
    private val epoch = admission.bootstrap.snapshot.epoch
    private val runId: String
    init {
        if (number !in 1..RoomWire.maximumCounter || watchGeneration !in 0..RoomWire.maximumCounter) throw RoomWire.bad()
        runId = admission.bootstrap.snapshot.members.firstOrNull { it.memberId == memberId }?.identity?.clientRunId ?: throw RoomWire.bad()
        listOf(roomId, memberId, epoch, runId).forEach(RoomWire::id)
        id = "cmd-$number"
        val type: String
        val payload: Map<String, Any?>
        when (action) {
            is RoomCommandAction.Catalog -> {
                RoomWire.id(action.batchId)
                val items = action.items.take(101)
                if (items.size > 100 || action.offset !in 0..RoomWire.maximumCounter - items.size ||
                    items.map { it.mediaId }.toSet().size != items.size) throw RoomWire.bad()
                type = "catalog.updated"
                payload = mapOf("batchId" to action.batchId, "offset" to action.offset, "items" to items.map(::media), "final" to action.final)
            }
            is RoomCommandAction.Select -> { RoomWire.id(action.mediaId); type = "selection.changed"; payload = mapOf("mediaId" to action.mediaId) }
            is RoomCommandAction.Start -> { RoomWire.id(action.mediaId); type = "watch.started"; payload = mapOf("mediaId" to action.mediaId) }
            is RoomCommandAction.End -> { type = "watch.ended"; payload = mapOf("reason" to action.reason.name) }
            is RoomCommandAction.Missing -> { RoomWire.id(action.mediaId); type = "media.missing"; payload = mapOf("mediaId" to action.mediaId, "missing" to action.missing) }
            is RoomCommandAction.Meet -> {
                RoomWire.validateMeetUri(action.uri)
                type = "call.linkChanged"; payload = mapOf("meetUri" to action.uri)
            }
        }
        wire = RoomWire.encode(mapOf("v" to 1L, "id" to id, "type" to type, "clientRunId" to runId, "roomEpoch" to epoch,
            "watchGeneration" to watchGeneration, "payload" to payload))
    }
    internal fun verify(admission: RoomAdmission) {
        if (admission.roomId != roomId || admission.memberId != memberId || admission.bootstrap.snapshot.epoch != epoch ||
            admission.bootstrap.snapshot.members.firstOrNull { it.memberId == memberId }?.identity?.clientRunId != runId) throw RoomWire.bad()
    }
    private fun media(value: MediaDescriptor): Map<String, Any?> = mutableMapOf<String, Any?>("v" to 1L, "mediaId" to value.mediaId,
        "title" to value.title, "titleKey" to value.titleKey, "fileSizeBytes" to value.fileSizeBytes, "durationMs" to value.durationMs)
        .apply { if (value.fullHashSha256 != null) put("fullHashSha256", value.fullHashSha256) }
}

class RoomCommandResult private constructor(val id: String, val sequence: Long, val errorCode: String?) {
    companion object {
        fun decode(bytes: ByteArray, command: RoomCommand): RoomCommandResult {
            val value = RoomWire.parse(bytes); RoomWire.keys(value, "v", "type", "id", "sequence", "error")
            if (RoomWire.integer(value["v"], 1) != 1L || value["type"] != "command.result" || value["id"] != command.id) throw RoomWire.bad()
            val error = RoomWire.optionalString(value["error"])
            val allowed = setOf("foreignRun", "staleEpoch", "staleGeneration", "unavailable", "conflict", "queueFull", "invalidState", "forbidden", "malformed", "frameTooLarge")
            if (error != null && error !in allowed) throw RoomWire.bad()
            return RoomCommandResult(command.id, RoomWire.integer(value["sequence"]), error)
        }
    }
}
