package syncwatch.room

import syncwatch.domain.MediaDescriptor
import kotlinx.coroutines.ensureActive

data class RoomCatalogEntry(val memberId: String, val media: MediaDescriptor)

/** A bootstrap and its complete catalog are published together; no partial view escapes. */
class RoomCatalogView private constructor(val bootstrap: RoomBootstrap, items: List<RoomCatalogEntry>) {
    val items: List<RoomCatalogEntry> = java.util.Collections.unmodifiableList(items.toList())
    companion object {
        suspend fun read(bootstrap: RoomBootstrap, fetch: suspend (String) -> ByteArray): RoomCatalogView {
            RoomCatalogPosition(bootstrap.catalogCursor, bootstrap)
            var cursor = bootstrap.catalogCursor
            val items = mutableListOf<RoomCatalogEntry>()
            val seen = mutableSetOf<Pair<String, String>>()
            val counts = mutableMapOf<String, Int>()
            while (true) {
                kotlinx.coroutines.currentCoroutineContext().ensureActive()
                val page = RoomCatalogPage.decode(fetch(cursor), bootstrap, cursor)
                kotlinx.coroutines.currentCoroutineContext().ensureActive()
                for (item in page.items) {
                    val count = (counts[item.memberId] ?: 0) + 1
                    // The service permits at most 2048 catalog items per member.
                    if (!seen.add(item.memberId to item.media.mediaId) || count > 2048) throw RoomWire.bad()
                    counts[item.memberId] = count
                }
                items.addAll(page.items)
                cursor = page.nextCursor ?: return RoomCatalogView(bootstrap, items)
            }
        }
    }
}

/** One bounded page of a bootstrap's stable view, never a partial replacement catalog. */
class RoomCatalogPage private constructor(val epoch: String, val sequence: Long, items: List<RoomCatalogEntry>, val nextCursor: String?) {
    val items: List<RoomCatalogEntry> = java.util.Collections.unmodifiableList(items.toList())
    companion object {
        fun decode(bytes: ByteArray, bootstrap: RoomBootstrap, cursor: String): RoomCatalogPage {
            val position = RoomCatalogPosition(cursor, bootstrap)
            val value = RoomWire.parse(bytes)
            RoomWire.keys(value, "v", "roomEpoch", "sequence", "items", "nextCursor")
            val entries = value["items"] as? List<*> ?: throw RoomWire.bad()
            if (RoomWire.integer(value["v"], 1) != 1L || RoomWire.string(value["roomEpoch"]) != bootstrap.snapshot.epoch ||
                RoomWire.integer(value["sequence"]) != bootstrap.snapshot.sequence || entries.size > 100) throw RoomWire.bad()
            val members = bootstrap.snapshot.members.map { it.memberId }.toSet()
            val seen = mutableSetOf<Pair<String, String>>()
            val items = entries.map { item ->
                val entry = RoomWire.obj(item); RoomWire.keys(entry, "memberId", "media")
                val member = RoomWire.string(entry["memberId"])
                if (member !in members) throw RoomWire.bad()
                val descriptor = RoomMedia.decode(entry["media"])
                if (!seen.add(member to descriptor.mediaId)) throw RoomWire.bad()
                RoomCatalogEntry(member, descriptor)
            }
            val next = RoomWire.optionalString(value["nextCursor"])
            if (next != null && (items.isEmpty() || RoomCatalogPosition(next, bootstrap).offset != position.offset + items.size)) throw RoomWire.bad()
            return RoomCatalogPage(bootstrap.snapshot.epoch, bootstrap.snapshot.sequence, items, next)
        }
    }
}

internal class RoomCatalogPosition(cursor: String, bootstrap: RoomBootstrap) {
    val offset: Long
    init {
        fun parse(value: String): Pair<String, Long> {
            val parts = value.split(':')
            if (parts.size != 2 || !parts[1].matches(Regex("0|[1-9][0-9]{0,15}"))) throw RoomWire.bad()
            RoomWire.id(parts[0])
            val number = parts[1].toLongOrNull()?.takeIf { it <= RoomWire.maximumCounter } ?: throw RoomWire.bad()
            return parts[0] to number
        }
        val initial = parse(bootstrap.catalogCursor); val current = parse(cursor)
        if (initial.second != 0L || initial.first != current.first) throw RoomWire.bad()
        offset = current.second
    }
}

internal object RoomMedia {
    fun decode(value: Any?): MediaDescriptor {
        val media = RoomWire.obj(value)
        val keys = listOf("v", "mediaId", "title", "titleKey", "fileSizeBytes", "durationMs") +
            if (media.containsKey("fullHashSha256")) listOf("fullHashSha256") else emptyList()
        RoomWire.keys(media, *keys.toTypedArray())
        if (RoomWire.integer(media["v"], 1) != 1L) throw RoomWire.bad()
        val descriptor = try {
            MediaDescriptor(RoomWire.string(media["mediaId"]), RoomWire.string(media["title"]), RoomWire.string(media["titleKey"]),
                RoomWire.integer(media["fileSizeBytes"]), media["durationMs"]?.let { RoomWire.integer(it) },
                if (media.containsKey("fullHashSha256")) RoomWire.string(media["fullHashSha256"]) else null)
        } catch (_: Exception) { throw RoomWire.bad() }
        return descriptor
    }
}
