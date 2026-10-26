package syncwatch.room

import syncwatch.domain.MediaDescriptor
import syncwatch.ipc.Json

private fun commandAction(entry: Map<String, Any?>): RoomCommandAction {
    val payload = RoomWire.obj(entry["payload"])
    return when (entry["type"]) {
        "catalog.updated" -> RoomCommandAction.Catalog(payload["batchId"] as String, payload["offset"] as Long,
            (payload["items"] as List<*>).map { raw -> val p = RoomWire.obj(raw)
                MediaDescriptor(p["mediaId"] as String, p["title"] as String, p["titleKey"] as String, p["fileSizeBytes"] as Long, p["durationMs"] as Long?, p["fullHashSha256"] as String?) }, payload["final"] as Boolean)
        "selection.changed" -> RoomCommandAction.Select(payload["mediaId"] as String)
        "watch.started" -> RoomCommandAction.Start(payload["mediaId"] as String)
        "watch.ended" -> RoomCommandAction.End(RoomWatchEndReason.valueOf(payload["reason"] as String))
        "media.missing" -> RoomCommandAction.Missing(payload["mediaId"] as String, payload["missing"] as Boolean)
        "call.linkChanged" -> RoomCommandAction.Meet(payload["meetUri"] as String?)
        else -> error("Unknown fixture command")
    }
}
suspend fun commandChecks(root: Map<String, Any?>) {
    val entry = (root["admissions"] as List<*>).map(RoomWire::obj).first { it["valid"] == true }
    val admission = RoomAdmission.decode((entry["wire"] as String).toByteArray(), RoomIdentity("run-room-client", "Room User"), true)
    val corpus = RoomWire.obj(root["commands"])
    for (raw in corpus["outgoing"] as List<*>) {
        val item = RoomWire.obj(raw)
        val result = runCatching { RoomCommand(admission, item["number"] as Long, item["generation"] as Long, commandAction(item)) }
        check(result.isSuccess == item["valid"]) { "command: ${item["name"]}" }
        if (result.isFailure) check(result.exceptionOrNull() is RoomProtocolException)
        result.getOrNull()?.let { command ->
            val original = command.encodedBytes; val copy = command.encodedBytes; copy[0] = (copy[0].toInt() xor 1).toByte()
            check(original.contentEquals(command.encodedBytes))
            val expected = mapOf("v" to 1L, "id" to command.id, "type" to item["type"], "clientRunId" to "run-room-client",
                "roomEpoch" to "epoch-room", "watchGeneration" to item["generation"], "payload" to item["payload"])
            check(Json.parse(String(original, Charsets.UTF_8)) == expected) { "command wire: ${item["name"]}" }
        }
    }
    val reference = RoomCommand(admission, 1, 0, RoomCommandAction.Select("movie-a"))
    for (raw in corpus["results"] as List<*>) {
        val item = RoomWire.obj(raw); val bytes = (item["wire"] as String).toByteArray(Charsets.UTF_8)
        val result = runCatching { RoomCommandResult.decode(bytes, reference) }
        check(result.isSuccess == item["valid"]) { "result: ${item["name"]}" }
        if (result.isFailure) check(result.exceptionOrNull() is RoomProtocolException)
        result.getOrNull()?.let { check(it.id == "cmd-1" && it.sequence == 7L && it.errorCode == RoomWire.obj(Json.parse(String(bytes, Charsets.UTF_8)))["error"]) }
    }
    fun media(i: Int, title: String) = MediaDescriptor("movie-$i", title, MediaDescriptor.normalizedTitleKey(title), 1, null, null)
    check(runCatching { RoomCommand(admission, 1, 0, RoomCommandAction.Catalog("batch-a", 0, (0 until 100).map { media(it, "😀".repeat(256)) }, true)) }.exceptionOrNull() is RoomProtocolException)
    check(runCatching { RoomCommand(admission, 1, 0, RoomCommandAction.Catalog("batch-a", 0, (0 until 101).map { media(it, "Movie") }, true)) }.exceptionOrNull() is RoomProtocolException)
    check(runCatching { RoomCommand(admission, -1, 0, RoomCommandAction.Select("movie-a")) }.exceptionOrNull() is RoomProtocolException)
    val foreign = RoomAdmission("room-other", admission.memberId, admission.token, admission.invitation, admission.expiresAt, admission.bootstrap)
    val client = RoomClient(RoomAddress("http://127.0.0.1:1"))
    try { check((runCatching { client.execute(foreign, reference) }.exceptionOrNull() as? RoomProtocolException)?.code == "malformed") }
    finally { client.close() }
    println("SYNCWATCH_ROOM_COMMANDS_OK")
}
