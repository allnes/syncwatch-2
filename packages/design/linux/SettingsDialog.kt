// SPDX-License-Identifier: Apache-2.0
package syncwatch.design

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.window.Popup
import androidx.compose.ui.window.PopupProperties
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// First-party source only; compiling/rendering remains gated by the Linux dependency closure.
enum class SettingsVisualState { editing, savedNotice, invalidConfiguration }
class SettingsEditor private constructor(
    initial: Map<String, String>, val editableFields: Set<String>, val canSave: Boolean,
    val state: SettingsVisualState, val message: String, baseline: Map<String, String>?,
) {
    val values: Map<String, String> = (SyncWatchSettings.defaults + initial).toMap()
    private val original: Map<String, String> = (baseline ?: values).toMap()
    constructor(values: Map<String, String> = emptyMap(), editableFields: Set<String> = emptySet(), canSave: Boolean = false,
        state: SettingsVisualState = SettingsVisualState.editing,
        message: String = if (state == SettingsVisualState.invalidConfiguration) "invalidConfiguration" else "") :
        this(values.toMap(), editableFields.toSet(), canSave, state, message, null)
    private fun updated(values: Map<String, String> = this.values, state: SettingsVisualState = this.state,
        message: String = this.message, original: Map<String, String> = this.original) =
        SettingsEditor(values, editableFields, canSave, state, message, original)
    fun edit(id: String, value: String): SettingsEditor = if (id in editableFields && id in SyncWatchSettings.defaults)
        updated(values = values + (id to value), state = SettingsVisualState.editing, message = "") else this
    val isValid: Boolean get() = values.keys == SyncWatchSettings.defaults.keys && editableFields.all { it in SyncWatchSettings.defaults } &&
        SyncWatchSettings.fields.all { descriptor -> values[descriptor.id]?.let { value ->
            value.length <= descriptor.maxLength && value.none { it.code < 32 || it.code in 127..159 } &&
                (descriptor.kind != "choice" || value in descriptor.options) && (descriptor.kind != "boolean" || value in setOf("true", "false"))
        } == true }
    fun save(persist: (Map<String, String>) -> Boolean): Pair<SettingsEditor, Boolean> {
        if (!canSave) return this to false
        if (!isValid) return updated(state = SettingsVisualState.invalidConfiguration, message = "invalidConfiguration") to false
        if (!persist(values.toMap())) return updated(state = SettingsVisualState.invalidConfiguration, message = "saveFailed") to false
        return updated(original = values.toMap(), state = SettingsVisualState.savedNotice, message = "changesSaved") to true
    }
    fun cancel() = updated(values = original.toMap(), state = SettingsVisualState.editing, message = "")
}

@Composable fun SettingsDialog(editor: SettingsEditor, onEditorChange: (SettingsEditor) -> Unit,
    language: String = "en", initialSection: String = "interface", theme: SyncWatchTheme = SyncWatchTheme.dark,
    onSave: (Map<String, String>) -> Boolean = { false }, onClose: () -> Unit = {}) {
    var section by remember { mutableStateOf(initialSection.takeIf { it in SyncWatchSettings.sections } ?: "interface") }
    fun text(key: String) = if (key.isEmpty()) "" else SyncWatchCopy.text(key, language)
    fun close() { onEditorChange(editor.cancel()); onClose() }
    @Composable fun compactButton(key: String, enabled: Boolean = true, filled: Boolean = false, clicked: () -> Unit) {
        val shape = RoundedCornerShape(SyncWatchTokens.controlButtonRadius.dp)
        Box(Modifier.alpha(if (enabled) 1f else .4f).height(SyncWatchTokens.layoutSettingsControlHeight.dp)
            .background(rgba(if (filled) theme.accent else theme.surfaceRaised), shape)
            .border(SyncWatchTokens.controlBorderWidth.dp, rgba(theme.border), shape)
            .clickable(enabled = enabled, role = Role.Button, onClick = clicked).padding(horizontal = SyncWatchTokens.layoutSettingsCardPadding.dp), contentAlignment = Alignment.Center) {
            Label(text(key), if (filled) theme.copy(text = SyncWatchTokens.colorDarkText) else theme)
        }
    }
    val shape = RoundedCornerShape(SyncWatchTokens.controlCompactDialogRadius.dp)
    Column(Modifier.size(SyncWatchTokens.layoutSettingsWidth.dp, SyncWatchTokens.layoutSettingsHeight.dp)
        .background(rgba(theme.surface), shape).border(SyncWatchTokens.controlBorderWidth.dp, rgba(theme.border), shape)) {
        Row(Modifier.fillMaxWidth().height(SyncWatchTokens.layoutSettingsHeaderHeight.dp).background(rgba(theme.backgroundDeep))
            .padding(horizontal = SyncWatchTokens.layoutSettingsCardPadding.dp), verticalAlignment = Alignment.CenterVertically) {
            Label(text("brand") + " · " + text("openSettings"), theme, bold = true, modifier = Modifier.weight(1f))
            compactButton("close") { close() }
        }
        Row(Modifier.weight(1f)) {
            Column(Modifier.width(SyncWatchTokens.layoutSettingsSidebarWidth.dp).fillMaxHeight().background(rgba(theme.backgroundDeep)).padding(SyncWatchTokens.layoutSettingsCardPadding.dp)) {
                SyncWatchSettings.sections.forEach { id ->
                    Box(Modifier.fillMaxWidth().heightIn(min = SyncWatchTokens.layoutSettingsSidebarRowHeight.dp)
                        .background(rgba(if (id == section) theme.selection else theme.backgroundDeep), RoundedCornerShape(SyncWatchTokens.controlFieldRadius.dp))
                        .clickable(role = Role.Tab) { section = id }.padding(horizontal = SyncWatchTokens.layoutSettingsCardPadding.dp), contentAlignment = Alignment.CenterStart) { Label(text(id), theme) }
                }
            }
            Column(Modifier.weight(1f).fillMaxHeight().verticalScroll(rememberScrollState()).padding(SyncWatchTokens.layoutSettingsContentPadding.dp), verticalArrangement = Arrangement.spacedBy(SyncWatchTokens.controlCompactGap.dp)) {
                Label(text(section), theme, size = SyncWatchTokens.typeSettingsSectionSize, bold = true)
                Label(text(section + "Hint"), theme, muted = true)
                SyncWatchSettings.fields.filter { it.section == section }.forEach { field ->
                    val enabled = field.id in editor.editableFields
                    val current = editor.values[field.id] ?: ""
                    Column(Modifier.widthIn(max = (if (field.section == "interface") SyncWatchTokens.layoutSettingsInterfaceFieldWidth else SyncWatchTokens.layoutSettingsFieldWidth).dp).fillMaxWidth().alpha(if (enabled) 1f else .4f)) {
                        if (field.kind != "boolean") Label(text(field.label), theme, muted = true, size = SyncWatchTokens.typeSettingsBodySize)
                        when (field.kind) {
                            "choice" -> {
                                var expanded by remember(field.id) { mutableStateOf(false) }
                                val popupOffset = with(LocalDensity.current) { SyncWatchTokens.layoutSettingsControlHeight.dp.roundToPx() }
                                Box {
                                    Box(Modifier.fillMaxWidth().height(SyncWatchTokens.layoutSettingsControlHeight.dp)
                                        .background(rgba(theme.inputFill), RoundedCornerShape(SyncWatchTokens.controlFieldRadius.dp))
                                        .border(SyncWatchTokens.controlBorderWidth.dp, rgba(theme.border), RoundedCornerShape(SyncWatchTokens.controlFieldRadius.dp))
                                        .clickable(enabled = enabled, role = Role.Button) { expanded = !expanded }
                                        .padding(horizontal = SyncWatchTokens.layoutSettingsCardPadding.dp), contentAlignment = Alignment.CenterStart) {
                                        Label(text("option" + current.replaceFirstChar { it.uppercaseChar() }), theme)
                                    }
                                    if (expanded) Popup(alignment = Alignment.TopStart, offset = IntOffset(0, popupOffset),
                                        onDismissRequest = { expanded = false }, properties = PopupProperties(focusable = true)) {
                                        Column(Modifier.width((if (field.section == "interface") SyncWatchTokens.layoutSettingsInterfaceFieldWidth else SyncWatchTokens.layoutSettingsFieldWidth).dp).background(rgba(theme.surfaceRaised))) {
                                            field.options.forEach { option ->
                                                Box(Modifier.fillMaxWidth().height(SyncWatchTokens.layoutSettingsControlHeight.dp)
                                                    .background(rgba(if (option == current) theme.selection else theme.surfaceRaised))
                                                    .clickable(role = Role.Button) { onEditorChange(editor.edit(field.id, option)); expanded = false }
                                                    .padding(horizontal = SyncWatchTokens.layoutSettingsCardPadding.dp), contentAlignment = Alignment.CenterStart) {
                                                    Label(text("option" + option.replaceFirstChar { it.uppercaseChar() }), theme)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            "boolean" -> Row(Modifier.fillMaxWidth().heightIn(min = SyncWatchTokens.layoutSettingsControlHeight.dp)
                                .toggleable(value = current == "true", enabled = enabled, role = Role.Switch, onValueChange = { onEditorChange(editor.edit(field.id, if (it) "true" else "false")) }), verticalAlignment = Alignment.CenterVertically) {
                                Label(text(field.label), theme, size = SyncWatchTokens.typeSettingsBodySize, modifier = Modifier.weight(1f))
                                Box(Modifier.size(SyncWatchTokens.controlSettingsToggleWidth.dp, SyncWatchTokens.controlSettingsToggleHeight.dp)
                                    .background(rgba(if (current == "true") theme.accent else theme.border), RoundedCornerShape((SyncWatchTokens.controlSettingsToggleHeight / 2).dp))
                                    .padding(horizontal = SyncWatchTokens.controlSettingsToggleInset.dp), contentAlignment = if (current == "true") Alignment.CenterEnd else Alignment.CenterStart) {
                                    Box(Modifier.size(SyncWatchTokens.controlSettingsToggleThumb.dp).background(rgba(SyncWatchTokens.colorDarkText), CircleShape))
                                }
                            }
                            else -> BasicTextField(current, { onEditorChange(editor.edit(field.id, it)) }, enabled = enabled, singleLine = true,
                                textStyle = TextStyle(color = rgba(theme.text), fontSize = SyncWatchTokens.typeSettingsBodySize.sp),
                                modifier = Modifier.fillMaxWidth().height(SyncWatchTokens.layoutSettingsControlHeight.dp).background(rgba(theme.inputFill), RoundedCornerShape(SyncWatchTokens.controlFieldRadius.dp))
                                    .semantics { contentDescription = text(field.label) }, decorationBox = { input -> Box(Modifier.padding(horizontal = SyncWatchTokens.layoutSettingsCardPadding.dp), contentAlignment = Alignment.CenterStart) { input() } })
                        }
                    }
                }
                if (SyncWatchSettings.fields.none { it.section == section && it.id in editor.editableFields }) Label(text("settingsUnavailable"), theme, muted = true)
            }
        }
        Row(Modifier.fillMaxWidth().height(SyncWatchTokens.layoutSettingsFooterHeight.dp).padding(horizontal = SyncWatchTokens.layoutSettingsCardPadding.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(SyncWatchTokens.controlCompactGap.dp)) {
            Label(text(if (!editor.canSave) "settingsReadOnly" else if (editor.state == SettingsVisualState.savedNotice) "changesSaved" else editor.message), theme, muted = true, modifier = Modifier.weight(1f))
            compactButton("cancel") { close() }
            compactButton("save", editor.canSave, true) { onEditorChange(editor.save(onSave).first) }
        }
    }
}


@Composable fun SettingsGallery() {
    var section by remember { mutableStateOf("interface") }
    var state by remember { mutableStateOf(SettingsVisualState.editing) }
    var language by remember { mutableStateOf("en") }
    var dark by remember { mutableStateOf(true) }
    var fail by remember { mutableStateOf(false) }
    var editor by remember { mutableStateOf(SettingsEditor(editableFields = SyncWatchSettings.defaults.keys, canSave = true)) }
    val theme = if (dark) SyncWatchTheme.dark else SyncWatchTheme.light
    Column(Modifier.fillMaxSize().background(rgba(theme.background))) {
        Row(Modifier.padding(SyncWatchTokens.layoutPanelPadding.dp), horizontalArrangement = Arrangement.spacedBy(SyncWatchTokens.controlCompactGap.dp)) {
            Action(section, true, theme) { section = SyncWatchSettings.sections[(SyncWatchSettings.sections.indexOf(section) + 1) % SyncWatchSettings.sections.size] }
            Action(state.name, true, theme) { state = SettingsVisualState.entries[(state.ordinal + 1) % SettingsVisualState.entries.size]; editor = SettingsEditor(editableFields = SyncWatchSettings.defaults.keys, canSave = true, state = state) }
            Action(language, true, theme) { language = if (language == "en") "ru" else "en" }
            Action(if (dark) "dark" else "light", true, theme) { dark = !dark }
            Action("Fail save: $fail", true, theme) { fail = !fail }
        }
        Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
            key(section) { SettingsDialog(editor, { editor = it }, language, section, theme, onSave = { !fail }) }
        }
    }
}
