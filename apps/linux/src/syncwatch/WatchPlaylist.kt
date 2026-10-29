package syncwatch

import androidx.compose.runtime.*
import syncwatch.design.*
import java.util.UUID

/** Correlate catalog choices with one current watch. Common Design owns rendering. */
internal class WatchPlaylist {
    private val sourceID = "playlist-" + UUID.randomUUID()
    private var snapshot = SelectionMenuPresentation()
    private var closed = false
    private var neighborIDs: Set<String> = emptySet()
    var menu by mutableStateOf<SelectionMenuPresentation?>(null)
        private set

    fun update(entries: List<SelectionMenuEntry>, selectedID: String?, enabled: Boolean, neighborIDs: Set<String>? = null) {
        val neighbors = neighborIDs?.toSet() ?: entries.map { it.id }.toSet()
        val selected = selectedID?.takeIf { id -> entries.any { it.id == id } }
        if (closed || (snapshot.entries == entries && snapshot.selectedID == selected && snapshot.enabled == enabled && this.neighborIDs == neighbors)) return
        if (snapshot.revision >= SyncWatchSelectionMenu.maximumRevision) { close(); return }
        snapshot = SelectionMenuPresentation(kind = "playlist", sourceID = sourceID, revision = snapshot.revision + 1,
            entries = entries.toList(), selectedID = selected, enabled = enabled)
        this.neighborIDs = neighbors
        menu = null
    }
    fun open() { if (!closed && snapshot.isValid) menu = snapshot }
    fun dismiss() { menu = null }
    fun close() { closed = true; menu = null; snapshot = SelectionMenuPresentation() }
    fun neighbor(direction: Int): String? {
        if (closed || !snapshot.isValid || !snapshot.enabled || direction !in setOf(-1, 1)) return null
        val index = snapshot.entries.indexOfFirst { it.id == snapshot.selectedID }
        if (index < 0) return null
        var next = index + direction
        while (next in snapshot.entries.indices) {
            val entry = snapshot.entries[next]
            if (entry.enabled && entry.id in neighborIDs) return entry.id
            next += direction
        }
        return null
    }
    fun selection(request: SelectionMenuRequest): String? {
        val menu = menu ?: return null
        if (closed || request.kind != snapshot.kind || request.scope != "shared" || request.action != snapshot.definition?.action ||
            request.sourceID != sourceID || request.revision != snapshot.revision || menu.contextToken != snapshot.contextToken || !snapshot.allows(request.entryID)) return null
        dismiss(); return request.entryID
    }
    fun presentation(source: PlayerPresentation): PlayerPresentation {
        val enabled = source.enabledActions.toMutableSet().apply { removeAll(setOf("openPlaylist", "previousFile", "nextFile")) }
        val previous = neighbor(-1) != null; val next = neighbor(1) != null
        if (!closed && snapshot.isValid && snapshot.entries.isNotEmpty()) enabled += "openPlaylist"
        if (previous) enabled += "previousFile"
        if (next) enabled += "nextFile"
        return source.copy(enabledActions = enabled, hasPrevious = previous, hasNext = next)
    }
}
