package syncwatch.room

import java.nio.file.Files
import java.nio.file.Path
import syncwatch.ipc.Json

internal fun selectionChecks(path: Path) {
    val fixture = RoomWire.obj(Json.parse(Files.readString(path)))
    for (item in fixture["cases"] as List<*>) {
        val entry = RoomWire.obj(item)
        val bootstrap = RoomBootstrap.decode((entry["bootstrap"] as String).toByteArray(Charsets.UTF_8))
        val result = runCatching { RoomSelectionDefinition.decode((entry["wire"] as String).toByteArray(Charsets.UTF_8), bootstrap) }
        check(result.isSuccess == entry["valid"]) { "selection: ${entry["name"]}" }
        if (result.isFailure) check(result.exceptionOrNull() is RoomProtocolException)
        result.getOrNull()?.let {
            check(it.selection?.media?.mediaId == bootstrap.snapshot.mediaId && it.watchGeneration == bootstrap.snapshot.watchGeneration)
            it.selection?.let { selected -> check(selected.memberId == "departed-member" && selected.media.fileSizeBytes == 1000L) }
        }
    }
    println("SYNCWATCH_ROOM_SELECTION_OK")
}
