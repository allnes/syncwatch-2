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
    fun prepare(files: List<LocalMediaFile>): Publication {
        require(files.size <= 2048) { "catalog-limit" }
        val next = mutableMapOf<String, String>()
        val items = files.map { file ->
            val id = acknowledged[file.id] ?: pending[file.id] ?: ("media-" + java.util.UUID.randomUUID())
            check(next.put(file.id, id) == null) { "catalog-duplicate" }
            val title = MediaDescriptor.logicalTitle(file.title)
            MediaDescriptor(id, title, MediaDescriptor.normalizedTitleKey(title), file.sizeBytes, null, null)
        }
        pending = next
        return Publication(items, next)
    }
    fun acknowledge(publication: Publication) { acknowledged = publication.localIds }
    fun localId(roomId: String): String? = acknowledged.entries.firstOrNull { it.value == roomId }?.key
}
