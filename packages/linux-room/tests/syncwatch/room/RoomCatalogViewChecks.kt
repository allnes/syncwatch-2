package syncwatch.room

import kotlinx.coroutines.*

internal suspend fun catalogViewChecks(fixture: Map<String, Any?>) {
    val bootstrap = RoomBootstrap.decode((fixture["catalogBootstrap"] as String).toByteArray(Charsets.UTF_8))
    suspend fun read(pages: List<String>): RoomCatalogView {
        var index = 0
        val result = RoomCatalogView.read(bootstrap) { cursor ->
            check(index < pages.size)
            val expected = if (index == 0) "view-1:0" else RoomWire.parse(pages[index - 1].toByteArray(Charsets.UTF_8))["nextCursor"]
            check(cursor == expected) { "Unexpected cursor order" }
            pages[index++].toByteArray(Charsets.UTF_8)
        }
        check(index == pages.size)
        return result
    }
    for (raw in fixture["catalogViews"] as List<*>) {
        val item = RoomWire.obj(raw)
        val pages = (item["pages"] as List<*>).map { it as String }
        val result = runCatching { read(pages) }
        check(result.isSuccess == item["valid"]) { "catalog view: ${item["name"]}" }
        result.getOrNull()?.let {
            check(it.bootstrap == bootstrap && it.items.size.toLong() == item["count"])
            check(runCatching { (it.items as MutableList<RoomCatalogEntry>).clear() }.isFailure)
        }
        if (result.isFailure) check(result.exceptionOrNull() is RoomProtocolException)
    }
    for (count in listOf(2048, 2049)) {
        val pages = (0 until count step 100).map { start ->
            val end = minOf(start + 100, count)
            RoomWire.encode(mapOf("v" to 1, "roomEpoch" to "epoch-room", "sequence" to 7,
                "items" to (start until end).map { index -> mapOf("memberId" to "member-owner", "media" to mapOf(
                    "v" to 1, "mediaId" to "movie-$index", "title" to "Movie", "titleKey" to "movie", "fileSizeBytes" to 1024, "durationMs" to null)) },
                "nextCursor" to if (end < count) "view-1:$end" else null)).toString(Charsets.UTF_8)
        }
        val result = runCatching { read(pages) }
        check(result.isSuccess == (count == 2048))
        result.getOrNull()?.let { check(it.items.size == count) }
    }
    val terminal = """{"v":1,"roomEpoch":"epoch-room","sequence":7,"items":[],"nextCursor":null}""".toByteArray(Charsets.UTF_8)
    supervisorScope {
        val cancelled = async {
            RoomCatalogView.read(bootstrap) { currentCoroutineContext().cancel(); terminal }
        }
        check(runCatching { cancelled.await() }.exceptionOrNull() is CancellationException)
    }
    val expired = runCatching { RoomCatalogView.read(bootstrap) { throw RoomProtocolException("snapshotRequired") } }
    check((expired.exceptionOrNull() as? RoomProtocolException)?.code == "snapshotRequired")
    println("SYNCWATCH_ROOM_CATALOG_VIEW_OK complete/duplicate/version/bound/cancellation/expiry")
}
