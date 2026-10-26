package syncwatch

import syncwatch.domain.MediaDescriptor
import syncwatch.library.LocalMediaFile

/** Local file identifiers never become room identifiers. One map lives for one membership. */
internal class RoomLocalCatalog {
    class Publication(items: List<MediaDescriptor>, localIds: Map<String, String>) {
        val items: List<MediaDescriptor> = java.util.Collections.unmodifiableList(items.toList())
        val localIds: Map<String, String> = java.util.Collections.unmodifiableMap(localIds.toMap())
    }
    private var acknowledged = emptyMap<String, String>()
    private var pending = emptyMap<String, String>()
    fun prepare(files: List<LocalMediaFile>, prepared: MediaDescriptor? = null): Publication {
        val extra = if (prepared != null && files.none { it.id == prepared.mediaId }) 1 else 0
        require(files.size + extra <= 2048 && (prepared == null || prepared.fullHashSha256 != null && (prepared.durationMs ?: 0) > 0)) { "catalog-limit" }
        val next = mutableMapOf<String, String>()
        val items = mutableListOf<MediaDescriptor>()
        fun add(localId: String, title: String, size: Long, duration: Long?, hash: String?) {
            val id = acknowledged[localId] ?: pending[localId] ?: ("media-" + java.util.UUID.randomUUID())
            check(next.put(localId, id) == null) { "catalog-duplicate" }
            items.add(MediaDescriptor(id, title, MediaDescriptor.normalizedTitleKey(title), size, duration, hash))
        }
        for (file in files) {
            if (prepared != null && file.id == prepared.mediaId) add(file.id, prepared.title, prepared.fileSizeBytes, prepared.durationMs, prepared.fullHashSha256)
            else add(file.id, MediaDescriptor.logicalTitle(file.title), file.sizeBytes, null, null)
        }
        if (prepared != null && prepared.mediaId !in next) add(prepared.mediaId, prepared.title, prepared.fileSizeBytes, prepared.durationMs, prepared.fullHashSha256)
        pending = next
        return Publication(items, next)
    }
    fun acknowledge(publication: Publication) { acknowledged = publication.localIds }
    fun localId(roomId: String): String? = acknowledged.entries.firstOrNull { it.value == roomId }?.key
    fun roomId(localId: String): String? = acknowledged[localId]
}
