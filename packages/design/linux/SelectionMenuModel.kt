// SPDX-License-Identifier: Apache-2.0
package syncwatch.design

data class SelectionMenuEntry(val id: String, val label: String, val enabled: Boolean = true)
data class SelectionMenuRequest(
    val kind: String,
    val sourceID: String,
    val revision: Long,
    val entryID: String,
    val action: String,
    val scope: String,
)

// Provider observations only. Dispatch never changes the observed selection.
data class SelectionMenuPresentation(
    val kind: String = "playlist",
    val sourceID: String = "",
    val revision: Long = 0,
    val entries: List<SelectionMenuEntry> = emptyList(),
    val selectedID: String? = null,
    val enabled: Boolean = false,
) {
    val definition get() = SyncWatchSelectionMenu.kinds.firstOrNull { it.id == kind }
    val contextToken get() = "$kind|$sourceID|$revision"

    private fun validID(value: String) =
        value.length <= SyncWatchSelectionMenu.maximumIDBytes && Regex("[A-Za-z0-9._:-]+").matches(value)

    private fun validEntry(entry: SelectionMenuEntry) =
        validID(entry.id) && entry.label.isNotEmpty() &&
            entry.label.toByteArray(Charsets.UTF_8).size <= SyncWatchSelectionMenu.maximumLabelBytes &&
            entry.label.none { c -> c.code < 32 || c.code == 127 }

    val isValid get() = definition != null && validID(sourceID) &&
        revision in 0..SyncWatchSelectionMenu.maximumRevision &&
        entries.size <= SyncWatchSelectionMenu.maximumEntries &&
        entries.map { it.id }.toSet().size == entries.size && entries.all(::validEntry) &&
        (selectedID == null || entries.any { it.id == selectedID })

    fun allows(id: String) = isValid && enabled && id != selectedID && entries.any { it.id == id && it.enabled }

    fun dispatch(id: String, contextToken: String, handler: (SelectionMenuRequest) -> Unit) {
        val d = definition ?: return
        if (contextToken == this.contextToken && allows(id)) {
            handler(SelectionMenuRequest(kind, sourceID, revision, id, d.action, d.scope))
        }
    }
}
