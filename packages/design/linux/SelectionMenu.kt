// SPDX-License-Identifier: Apache-2.0
package syncwatch.design

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

// Native event binding; the common document owns layout and copy.
@Composable fun SelectionMenu(
    presentation: SelectionMenuPresentation = SelectionMenuPresentation(),
    language: String = "en",
    theme: SyncWatchTheme = SyncWatchTheme.dark,
    modifier: Modifier = Modifier,
    onSelection: (SelectionMenuRequest) -> Unit = {},
) {
    // Copy the accepted observation; one overflow entry preserves invalidity with bounded allocation.
    val snapshot = presentation.copy(entries = presentation.entries.take(SyncWatchSelectionMenu.maximumEntries + 1))
    DesignSurface("SelectionMenu", SelectionMenuBindings.context(snapshot), language, theme, modifier) { event ->
        if (event.action == "selectEntry" && event.value != null && event.payload != null) {
            snapshot.dispatch(event.value, event.payload, onSelection)
        }
    }
}

internal object SelectionMenuBindings {
    fun context(p: SelectionMenuPresentation): DesignContext {
        val entries = if (p.isValid) p.entries else emptyList()
        return DesignContext(
            mapOf(
                "kind" to p.kind,
                "menuLabel" to (p.definition?.label ?: "selectionUnavailable"),
                "contextToken" to p.contextToken,
                "entryCount" to entries.size.toString(),
                "hasEntries" to entries.isNotEmpty().toString(),
                "emptyLabel" to if (p.isValid) "selectionEmpty" else "selectionUnavailable",
            ),
            mapOf("entries" to entries.map { entry ->
                DesignContext(mapOf(
                    "id" to entry.id,
                    "label" to entry.label,
                    "selected" to (p.selectedID == entry.id).toString(),
                    "enabled" to (p.enabled && entry.enabled).toString(),
                    "disabledTrack" to entry.disabledTrack.toString(),
                ))
            }),
        )
    }
}
