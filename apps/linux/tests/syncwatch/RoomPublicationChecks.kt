package syncwatch

import java.nio.file.Files
import java.nio.file.Path
import kotlinx.coroutines.withContext
import org.jetbrains.skiko.MainUIDispatcher
import syncwatch.domain.MediaDescriptor
import syncwatch.ipc.Json
import syncwatch.library.FileSystemLibrary
import syncwatch.room.*

internal suspend fun roomPublicationChecks(fixtureFile: Path) = withContext(MainUIDispatcher) {
    val directory = Files.createTempDirectory("syncwatch-room-publication-")
    try {
        Files.writeString(directory.resolve("Movie.mkv"), "authored metadata fixture")
        val files = FileSystemLibrary().scan(directory, java.util.UUID.randomUUID().toString(), false)
        val map = RoomLocalCatalog(); val publication = map.prepare(files); val id = publication.items.single().mediaId
        check(id != files.single().id && publication.items.single().title == "Movie")
        check(map.prepare(files).items.single().mediaId == id && map.localId(id) == null)
        map.acknowledge(publication)
        check(map.localId(id) == files.single().id && RoomLocalCatalog().prepare(files).items.single().mediaId != id)
        val local = files.single()
        val strong = MediaDescriptor(local.id, "Movie", "movie", local.sizeBytes, 1234, "a".repeat(64))
        val loaded = map.prepare(files, strong)
        check(loaded.items.single().mediaId == id && loaded.items.single().fullHashSha256 == strong.fullHashSha256 && loaded.items.single().durationMs == 1234L && loaded.localIds[local.id] == id)
        map.acknowledge(loaded)
        check(map.prepare(emptyList(), strong).items == loaded.items && map.prepare(files).items.single().fullHashSha256 == null)
        check(runCatching { map.prepare(files, MediaDescriptor(local.id, "Movie", "movie", local.sizeBytes, 1234, null)) }.isFailure)
        map.acknowledge(map.prepare(emptyList())); check(map.localId(id) == null)

        @Suppress("UNCHECKED_CAST")
        val fixture = Json.parse(Files.readString(fixtureFile)) as Map<String, Any?>
        @Suppress("UNCHECKED_CAST")
        val admitted = (fixture["admissions"] as List<Map<String, Any?>>).first { it["valid"] == true && it["owner"] == true }
        val admission = RoomAdmission.decode((admitted["wire"] as String).toByteArray(Charsets.UTF_8), RoomIdentity("run-room-client", "Room User"), true)
        val title = "😀".repeat(256)
        val items = (0 until 100).map { MediaDescriptor("movie-$it", title, title, 1024, null, null) }
        var offset = 0; var number = 1L
        do {
            val batch = RoomMembershipSession.catalogCommand(admission, number++, 0, "batch-test", items, offset)
            check(batch.second in 1..100 && batch.first.encodedBytes.size <= 65536)
            @Suppress("UNCHECKED_CAST")
            val wire = Json.parse(batch.first.encodedBytes.toString(Charsets.UTF_8)) as Map<String, Any?>
            @Suppress("UNCHECKED_CAST")
            val payload = wire["payload"] as Map<String, Any?>
            check(payload["offset"] == offset.toLong() && (payload["items"] as List<*>).size == batch.second && payload["final"] == (offset + batch.second == items.size))
            offset += batch.second
        } while (offset < items.size)
        check(number > 2 && offset == 100 && RoomMembershipSession.catalogCommand(admission, number, 0, "batch-empty", emptyList(), 0).second == 0)
        println("SYNCWATCH_ROOM_PUBLICATION_MODEL_OK opaque identity/unicode byte bounds/empty clear")
    } finally {
        Files.walk(directory).use { it.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
    }
}
