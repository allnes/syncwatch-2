// SPDX-License-Identifier: Apache-2.0
package syncwatch.design

import androidx.compose.runtime.*

internal object SelectionMenuFixtures {
    fun presentation(kind: String, state: String, language: String = "en"): SelectionMenuPresentation {
        val definition = SyncWatchSelectionMenu.kinds.single { it.id == kind }
        val count = if (state == "empty") 0 else if (state == "longList") SyncWatchSelectionMenu.galleryEntryCount else 3
        val entries = (0 until count).map { i -> SelectionMenuEntry("item$i", SyncWatchCopy.text(if (state == "longList") "selectionFixtureLong" else definition.label, language) + " ${i + 1}", i != 2) }
        return SelectionMenuPresentation(kind, "fixture-$kind", 1, entries, entries.firstOrNull()?.id, state != "readOnly")
    }
}

// Source-only in-memory gallery. Common Gallery/selectionFixture trees own placement.
@Composable fun SelectionMenuGallery() {
    var kind by remember { mutableStateOf("playlist") }; var state by remember { mutableStateOf("available") }
    var language by remember { mutableStateOf("en") }; var dark by remember { mutableStateOf(true) }
    var revision by remember { mutableStateOf(1L) }; var selectedID by remember { mutableStateOf<String?>(null) }
    var lastAction by remember { mutableStateOf("") }
    val theme = if (dark) SyncWatchTheme.dark else SyncWatchTheme.light
    var p = SelectionMenuFixtures.presentation(kind, state, language).copy(revision = revision)
    if (p.entries.any { it.id == selectedID }) p = p.copy(selectedID = selectedID)
    fun choice(id: String, value: String, options: List<String>) = DesignContext(mapOf("id" to id, "label" to "gallery" + id.replaceFirstChar { it.uppercase() }, "kind" to "choice", "value" to value, "editable" to "true"), mapOf("options" to options.map { DesignContext(mapOf("id" to it, "label" to it)) }))
    val controls = listOf(choice("kind", kind, SyncWatchSelectionMenu.kinds.map { it.id }), choice("state", state, SyncWatchSelectionMenu.states), choice("language", language, listOf("en", "ru")), DesignContext(mapOf("id" to "dark", "label" to "galleryDark", "kind" to "boolean", "value" to dark.toString(), "editable" to "true")))
    DesignSurface("Gallery", DesignContext(mapOf("lastAction" to lastAction), mapOf("galleryControls" to controls)), language, theme, slots = mapOf("galleryContent" to {
        DesignSurface("selectionFixture", language = language, theme = theme, slots = mapOf("selectionFixtureContent" to {
            SelectionMenu(p, language, theme) { request -> selectedID = request.entryID; revision++; lastAction = request.scope + ":" + request.action }
        }))
    })) { e ->
        if (e.action == "gallery" && e.value != null) {
            when (e.payload) { "kind" -> kind = e.value; "state" -> state = e.value; "language" -> language = e.value; "dark" -> dark = e.value == "true" }
            selectedID = null; revision++
        }
    }
}
