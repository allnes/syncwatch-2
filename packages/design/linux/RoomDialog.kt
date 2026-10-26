package syncwatch.design

import androidx.compose.runtime.*

/** Memory-only connection draft; never persists credentials. */
class RoomEditor private constructor(initial: Map<String, String>, val mode: String, val state: String, val status: String,
    val roomId: String, val memberCount: Int, val owner: Boolean) {
    val values: Map<String, String> = java.util.Collections.unmodifiableMap(HashMap(initial))
    constructor(initial: Map<String, String> = emptyMap()) : this(SyncWatchRoomForm.defaults + initial.filterKeys { id ->
        SyncWatchRoomForm.fields.any { it.id == id && it.kind != "secret" } }, "createRoom", "disconnected", "", "", 0, false)
    val busy: Boolean get() = state == "connecting"
    val connected: Boolean get() = state == "connected"
    val fields: List<SyncWatchRoomFormField> get() = SyncWatchRoomForm.fields.filter { it.section == "connection" || it.section == mode }
    val isValid: Boolean get() = fields.all { field -> values[field.id]?.let { value ->
        value.isNotEmpty() && value.length <= field.maxLength && value.none { it.code < 32 || it.code == 127 } } == true }
    fun copy(state: String = this.state, status: String = this.status, roomId: String = this.roomId, memberCount: Int = this.memberCount,
        owner: Boolean = this.owner) = RoomEditor(values, mode, state, status, roomId, memberCount, owner)
    fun edit(id: String, value: String): RoomEditor {
        if (busy || connected || fields.none { it.id == id && value.length <= it.maxLength }) return this
        return RoomEditor(values + (id to value), mode, state, "", roomId, memberCount, owner)
    }
    fun selectMode(mode: String): RoomEditor = if (busy || connected || mode == this.mode || mode !in listOf("createRoom", "joinRoom")) this else
        RoomEditor(clearSecrets().values, mode, state, "", roomId, memberCount, owner)
    fun clearSecrets(): RoomEditor = RoomEditor(values + SyncWatchRoomForm.fields.filter { it.kind == "secret" }.associate { it.id to "" }, mode, state, status, roomId, memberCount, owner)
    val context: DesignContext get() = DesignContext(mapOf("namespace" to "room", "showForm" to (!connected).toString(), "connected" to connected.toString(),
        "createMode" to (mode == "createRoom").toString(), "joinMode" to (mode == "joinRoom").toString(), "connectLabel" to mode,
        "status" to if (busy) "roomConnecting" else status, "roomID" to roomId, "memberCount" to memberCount.toString(),
        "can.close" to "true", "can.chooseRoomMode" to (!busy && !connected).toString(), "can.connectRoom" to (!busy && !connected && isValid).toString(),
        "can.leaveRoom" to connected.toString(), "can.copyInvitation" to (connected && owner).toString()),
        mapOf("fields" to fields.map { DesignContext(mapOf("id" to it.id, "label" to it.label, "value" to values[it.id].orEmpty(), "secret" to (it.kind == "secret").toString(), "editable" to (!busy).toString())) }))
}
@Composable fun RoomDialog(editor: RoomEditor, onEditorChange: (RoomEditor) -> Unit, language: String = "en", theme: SyncWatchTheme = SyncWatchTheme.dark,
    onAction: (String) -> Unit = {}) {
    DesignSurface("Room", editor.context, language, theme) { event -> when (event.action) {
        "editRoomField" -> if (event.payload != null && event.value != null) onEditorChange(editor.edit(event.payload, event.value))
        "chooseRoomMode" -> event.payload?.let { onEditorChange(editor.selectMode(it)) }
        else -> onAction(event.action)
    } }
}
