package syncwatch.room

import java.nio.file.Files
import java.nio.file.Path
import syncwatch.ipc.Json

fun main(args: Array<String>) {
    val fixture = RoomWire.obj(Json.parse(Files.readString(Path.of(args[0]))))
    val identity = RoomIdentity("run-room-client", "Room User")
    for (entry in fixture["addresses"] as List<*>) {
        val item = RoomWire.obj(entry)
        val accepted = runCatching { RoomAddress(item["value"] as String) }.isSuccess
        check(accepted == item["valid"]) { "address: ${item["value"]}" }
    }
    for (entry in fixture["admissions"] as List<*>) {
        val item = RoomWire.obj(entry)
        val result = runCatching { RoomAdmission.decode((item["wire"] as String).toByteArray(Charsets.UTF_8), identity, item["owner"] as Boolean) }
        check(result.isSuccess == item["valid"]) { "admission: ${item["name"]}" }
        result.getOrNull()?.let {
            check(it.memberId == "member-owner" && it.bootstrap.connection.port == 8999)
            check(!it.toString().contains("A".repeat(64)) && !it.toString().contains("B".repeat(64)))
        }
    }
    println("SYNCWATCH_ROOM_PROTOCOL_OK")
    kotlinx.coroutines.runBlocking { transportChecks() }
}
