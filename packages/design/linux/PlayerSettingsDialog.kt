// SPDX-License-Identifier: Apache-2.0
package syncwatch.design

import androidx.compose.runtime.*
import androidx.compose.ui.geometry.Offset
import kotlin.math.abs
import kotlin.math.round
import java.util.Locale


// First-party source only; compiler/Compose/native/font/license closure remains open.
enum class PlayerSettingsVisualState { editing, savedNotice, invalidConfiguration, readOnly }
class PlayerSettingsEditor private constructor(
    initial: Map<String, String>, capabilities: Set<String>, requestedSave: Boolean,
    requestedState: PlayerSettingsVisualState, val message: String, baseline: Map<String, String>?,
) {
    val values: Map<String, String> = (SyncWatchPlayerSettings.defaults + initial).toMap()
    val editableFields: Set<String> = capabilities.toSet()
    val canSave = requestedSave && requestedState != PlayerSettingsVisualState.readOnly
    val state = if (canSave) requestedState else PlayerSettingsVisualState.readOnly
    private val original = (baseline ?: values).toMap()
    constructor(values: Map<String, String> = emptyMap(), editableFields: Set<String> = emptySet(), canSave: Boolean = false,
        state: PlayerSettingsVisualState = PlayerSettingsVisualState.editing) :
        this(values, editableFields, canSave, state, when (state) {
            PlayerSettingsVisualState.savedNotice -> "changesSaved"
            PlayerSettingsVisualState.invalidConfiguration -> "invalidConfiguration"
            else -> ""
        }, null)
    private fun updated(values: Map<String, String> = this.values, state: PlayerSettingsVisualState = this.state,
        message: String = this.message, original: Map<String, String> = this.original) =
        PlayerSettingsEditor(values, editableFields, canSave, state, message, original)
    fun allows(id: String) = canSave && id in editableFields && id in SyncWatchPlayerSettings.defaults
    fun edit(id: String, value: String) = if (allows(id)) updated(values + (id to value), PlayerSettingsVisualState.editing, "") else this
    val isValid get() = values.keys == SyncWatchPlayerSettings.defaults.keys && editableFields.all { it in SyncWatchPlayerSettings.defaults } &&
        SyncWatchPlayerSettings.fields.all { valid(values[it.id].orEmpty(), it) }
    fun canReset(section: String) = section in SyncWatchPlayerSettings.sections && SyncWatchPlayerSettings.fields.any { it.section == section && allows(it.id) }
    fun reset(section: String): PlayerSettingsEditor {
        if (!canReset(section)) return this
        val defaults = SyncWatchPlayerSettings.fields.filter { it.section == section && allows(it.id) }.associate { it.id to SyncWatchPlayerSettings.defaults.getValue(it.id) }
        return updated(values + defaults, PlayerSettingsVisualState.editing, "")
    }
    fun save(persist: (Map<String, String>) -> Boolean): Pair<PlayerSettingsEditor, Boolean> {
        if (!canSave) return this to false
        if (!isValid) return updated(state = PlayerSettingsVisualState.invalidConfiguration, message = "invalidConfiguration") to false
        if (!persist(values.toMap())) return updated(state = PlayerSettingsVisualState.invalidConfiguration, message = "saveFailed") to false
        return updated(original = values, state = PlayerSettingsVisualState.savedNotice, message = "changesSaved") to true
    }
    fun cancel() = updated(values = original, state = if (canSave) PlayerSettingsVisualState.editing else PlayerSettingsVisualState.readOnly, message = "")
    companion object {
        private val decimal = Regex("-?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?")
        fun valid(value: String, field: PlayerSettingField): Boolean {
            if (value.length > 64 || value.any { it.code < 32 || it.code in 127..159 }) return false
            if (field.kind == "boolean") return value == "true" || value == "false"
            if (field.kind != "range") return field.options.any { it.id == value }
            if (!decimal.matches(value)) return false
            val number = value.toDoubleOrNull() ?: return false
            if (!number.isFinite() || number !in field.minimum..field.maximum) return false
            val ticks = (number - field.minimum) / field.step
            return abs(ticks - round(ticks)) < 1e-8
        }
        fun canonical(value: Double): String = if (!value.isFinite()) "" else
            String.format(Locale.ROOT, "%.2f", if (abs(value) < 1e-8) 0.0 else value).trimEnd('0').trimEnd('.')
    }
}

@Composable fun PlayerSubtitlePreview(values:Map<String,String>,language:String="en") { DesignSurface("subtitlePreview",DesignBindings.preview(values),language) }

@Composable fun PlayerSettingsDialog(editor:PlayerSettingsEditor,onEditorChange:(PlayerSettingsEditor)->Unit,language:String="en",initialSection:String="playback",theme:SyncWatchTheme=SyncWatchTheme.dark,
    onSave:(Map<String,String>)->Boolean={false},onClose:()->Unit={},onMove:(Offset)->Unit={}) {
    var section by remember {mutableStateOf(initialSection.takeIf{it in SyncWatchPlayerSettings.sections}?:"playback")};var lastDrag by remember{mutableStateOf(Offset.Zero)}
    DesignSurface("PlayerSettings",DesignBindings.playerSettings(editor,section,language),language,theme){event->when(event.action){
        "selectSection"->event.value?.takeIf{it in SyncWatchPlayerSettings.sections}?.let{section=it}
        "editField"->if(event.payload!=null&&event.value!=null){
            val field=SyncWatchPlayerSettings.fields.singleOrNull{it.id==event.payload};val number=event.value.toDoubleOrNull()
            val value=if(field?.kind=="range"&&number!=null)PlayerSettingsEditor.canonical(field.minimum+round((number-field.minimum)/field.step)*field.step)else event.value
            onEditorChange(editor.edit(event.payload,value))
        }
        "resetSection"->onEditorChange(editor.reset(section))
        "save"->onEditorChange(editor.save(onSave).first)
        "close","cancel"->{onEditorChange(editor.cancel());onClose()}
        "moveDialog"->if(event.value==null)lastDrag=Offset.Zero else {val point=event.value.split(',').mapNotNull{it.toFloatOrNull()};if(point.size==2){val current=Offset(point[0],point[1]);onMove(current-lastDrag);lastDrag=current}}
    }}
}
