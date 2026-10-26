// SPDX-License-Identifier: Apache-2.0
package syncwatch.design

import androidx.compose.runtime.*
import androidx.compose.ui.Modifier


// Source-only renderer until the pinned Compose/compiler/native graph is buildable.
// Foundation primitives deliberately avoid an additional Material theme dependency.
enum class LibraryVisualState { empty, scanning, selected, missingMedia, reconnecting }
data class LibraryEntry(val id: String, val title: String, val location: String)
data class LibraryPresentation(
    val state: LibraryVisualState = LibraryVisualState.empty,
    val entries: List<LibraryEntry> = emptyList(),
    val selectedID: String? = null,
    val enabledActions: Set<String> = emptySet(),
    val roomStatus: String = "",
) {
    val selected: LibraryEntry? get() = entries.firstOrNull { it.id == selectedID }
    fun allows(action: String): Boolean = action in enabledActions && action in SyncWatchCopy.libraryActions && when (action) {
        "startWatching" -> state == LibraryVisualState.selected && selected != null
        "selectMovie", "search" -> state != LibraryVisualState.scanning
        else -> true
    }
    fun dispatch(action: String, value: String? = null, handler: (String, String?) -> Unit) {
        if (allows(action) && (action != "selectMovie" || entries.any { it.id == value })) handler(action, value)
    }
    companion object {
        fun gallery(state: LibraryVisualState): LibraryPresentation {
            val entries = if (state == LibraryVisualState.empty || state == LibraryVisualState.scanning) emptyList() else
                SyncWatchCopy.galleryMovies.mapIndexed { index, title -> LibraryEntry(index.toString(), title, "Movies/$title") }
            return LibraryPresentation(state, entries, entries.firstOrNull()?.id,
                setOf("chooseFolder", "rescan", "search", "selectMovie", "startWatching", "openSettings"))
        }
    }
}

@Composable fun LibraryWorkspace(presentation: LibraryPresentation = LibraryPresentation(), language: String = "en",
    theme: SyncWatchTheme = SyncWatchTheme.dark, modifier: Modifier = Modifier, onAction: (String, String?) -> Unit = { _, _ -> }) {
    var query by remember { mutableStateOf("") }
    DesignSurface("Library", DesignBindings.library(presentation,query,language),language,theme,modifier) { event ->
        if(event.action=="search")query=event.value.orEmpty()
        presentation.dispatch(event.action,event.value,onAction)
    }
}
