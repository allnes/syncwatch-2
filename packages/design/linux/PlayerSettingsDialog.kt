// SPDX-License-Identifier: Apache-2.0
package syncwatch.design

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.key.*
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Popup
import androidx.compose.ui.window.PopupProperties
import java.util.Locale
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.round
import kotlin.math.sin

// First-party source only; compiler/Compose/native/font/license closure remains open.
enum class PlayerSettingsVisualState { editing, savedNotice, invalidConfiguration, readOnly }
class PlayerSettingsEditor private constructor(
    initial: Map<String, String>, capabilities: Set<String>, val canSave: Boolean,
    requestedState: PlayerSettingsVisualState, val message: String, baseline: Map<String, String>?,
) {
    val values: Map<String, String> = (SyncWatchPlayerSettings.defaults + initial).toMap()
    val editableFields: Set<String> = capabilities.toSet()
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

@Composable fun PlayerSubtitlePreview(values: Map<String, String>, language: String = "en") {
    fun number(id: String): Double {
        val field = SyncWatchPlayerSettings.fields.single { it.id == id }
        return (values[id]?.takeIf { PlayerSettingsEditor.valid(it, field) } ?: SyncWatchPlayerSettings.defaults.getValue(id)).toDouble()
    }
    BoxWithConstraints(Modifier.fillMaxWidth().height(SyncWatchTokens.layoutPlayerSettingsPreviewHeight.dp)
        .background(rgba(SyncWatchTokens.colorSharedVideoSurface)).clipToBounds()
        .semantics { contentDescription = SyncWatchCopy.text("subtitlePreview", language) }) {
        val size = number("subtitleSize").toFloat(); val padding = number("subtitlePadding").toFloat()
        val top = values["subtitlePosition"] == "top"
        val base = if (top) padding + size / 2 else maxHeight.value - padding - size / 2
        val position = (base + number("subtitleOffset").toFloat() / 120 * maxHeight.value * .34f * (if (top) 1 else -1)).coerceIn(size / 2, maxHeight.value - size / 2)
        val font = when (values["subtitleFont"]) { "serif" -> FontFamily.Serif; "monospace" -> FontFamily.Monospace; else -> FontFamily.Default }
        val style = TextStyle(fontFamily = font, fontSize = size.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
        val text = SyncWatchCopy.text("subtitlePreview", language)
        Box(Modifier.align(Alignment.TopCenter).offset(y = (position - size * .75f).dp).width((maxWidth.value - padding * 2).coerceAtLeast(1f).dp).height((size * 1.5f).dp), contentAlignment = Alignment.Center) {
            repeat(8) { i ->
                val outline = number("outlineWidth").toFloat()
                BasicText(text, Modifier.offset(x = (cos(i * Math.PI / 4).toFloat() * outline).dp, y = (sin(i * Math.PI / 4).toFloat() * outline).dp),
                    style.copy(color = rgba(SyncWatchPlayerSettings.color(values["outlineColor"].orEmpty()) ?: SyncWatchTokens.colorSubtitleBlack)), maxLines = 2)
            }
            BasicText(text, style = style.copy(color = rgba(SyncWatchPlayerSettings.color(values["subtitleColor"].orEmpty()) ?: SyncWatchTokens.colorSubtitleWhite)), maxLines = 2)
        }
    }
}

@Composable fun PlayerSettingsDialog(editor: PlayerSettingsEditor, onEditorChange: (PlayerSettingsEditor) -> Unit,
    language: String = "en", initialSection: String = "playback", theme: SyncWatchTheme = SyncWatchTheme.dark,
    onSave: (Map<String, String>) -> Boolean = { false }, onClose: () -> Unit = {}, onMove: (Offset) -> Unit = {}) {
    var section by remember { mutableStateOf(initialSection.takeIf { it in SyncWatchPlayerSettings.sections } ?: "playback") }
    val density = LocalDensity.current
    val currentMove by rememberUpdatedState(onMove)
    fun t(key: String) = if (key.isEmpty()) "" else SyncWatchCopy.text(key, language)
    fun close() { onEditorChange(editor.cancel()); onClose() }
    @Composable fun button(id: String, enabled: Boolean = true, filled: Boolean = false, clicked: () -> Unit) {
        val shape = RoundedCornerShape(SyncWatchTokens.controlButtonRadius.dp)
        Box(Modifier.height(SyncWatchTokens.layoutSettingsControlHeight.dp).alpha(if (enabled) 1f else .4f)
            .background(rgba(if (filled) theme.accent else theme.surfaceRaised), shape).border(SyncWatchTokens.controlBorderWidth.dp, rgba(theme.border), shape)
            .clickable(enabled, role = Role.Button, onClick = clicked).padding(horizontal = SyncWatchTokens.layoutSettingsCardPadding.dp), contentAlignment = Alignment.Center) {
            Label(t(id), if (filled) theme.copy(text = SyncWatchTokens.colorDarkText) else theme)
        }
    }
    @Composable fun field(field: PlayerSettingField, modifier: Modifier) {
        val enabled = editor.allows(field.id); val value = editor.values[field.id].orEmpty()
        Column(modifier, verticalArrangement = Arrangement.spacedBy(SyncWatchTokens.controlBorderWidth.dp)) {
            if (field.kind != "boolean") Row {
                Label(t(field.label), theme, muted = true, modifier = Modifier.weight(1f))
                if (field.kind == "range") Label(value + if (field.unit == "unitNone") "" else " " + t(field.unit), theme)
            }
            when (field.kind) {
                "boolean" -> Row(Modifier.fillMaxWidth().heightIn(min = SyncWatchTokens.layoutSettingsControlHeight.dp).alpha(if (enabled) 1f else .4f)
                    .toggleable(value == "true", enabled, Role.Switch) { onEditorChange(editor.edit(field.id, it.toString())) }, verticalAlignment = Alignment.CenterVertically) {
                    Label(t(field.label), theme, modifier = Modifier.weight(1f))
                    Box(Modifier.size(SyncWatchTokens.controlSettingsToggleWidth.dp, SyncWatchTokens.controlSettingsToggleHeight.dp)
                        .background(rgba(if (value == "true") theme.accent else theme.border), CircleShape).padding(horizontal = SyncWatchTokens.controlSettingsToggleInset.dp),
                        contentAlignment = if (value == "true") Alignment.CenterEnd else Alignment.CenterStart) {
                        Box(Modifier.size(SyncWatchTokens.controlSettingsToggleThumb.dp).background(rgba(SyncWatchTokens.colorDarkText), CircleShape))
                    }
                }
                "range" -> {
                    val number = (if (PlayerSettingsEditor.valid(value, field)) value else SyncWatchPlayerSettings.defaults.getValue(field.id)).toDouble()
                    PlayerRange(number - field.minimum, field.maximum - field.minimum, t(field.label), enabled, theme, Modifier.fillMaxWidth(), field.step) {
                        onEditorChange(editor.edit(field.id, PlayerSettingsEditor.canonical(field.minimum + floor(it / field.step + .5) * field.step)))
                    }
                }
                "color" -> Row(horizontalArrangement = Arrangement.spacedBy(SyncWatchTokens.controlCompactGap.dp)) {
                    field.options.forEach { option ->
                        Box(Modifier.alpha(if (enabled) 1f else .4f).border((SyncWatchTokens.controlBorderWidth * 2).dp, rgba(if (value == option.id) theme.accent else theme.border), CircleShape)
                            .clickable(enabled, role = Role.RadioButton) { onEditorChange(editor.edit(field.id, option.id)) }
                            .semantics { contentDescription = t(option.label); selected = value == option.id }
                            .padding((SyncWatchTokens.controlBorderWidth * 2).dp).size(SyncWatchTokens.layoutPlayerSettingsColorSize.dp)
                            .background(rgba(SyncWatchPlayerSettings.color(option.id) ?: theme.text), CircleShape))
                    }
                }
                else -> {
                    var expanded by remember(field.id) { mutableStateOf(false) }
                    val popupOffset = with(density) { SyncWatchTokens.layoutSettingsControlHeight.dp.roundToPx() }
                    Box {
                        Box(Modifier.fillMaxWidth().height(SyncWatchTokens.layoutSettingsControlHeight.dp).alpha(if (enabled) 1f else .4f)
                            .background(rgba(theme.inputFill), RoundedCornerShape(SyncWatchTokens.controlFieldRadius.dp))
                            .border(SyncWatchTokens.controlBorderWidth.dp, rgba(theme.border), RoundedCornerShape(SyncWatchTokens.controlFieldRadius.dp))
                            .clickable(enabled, role = Role.Button) { expanded = !expanded }.semantics { contentDescription = t(field.label) }
                            .padding(horizontal = SyncWatchTokens.layoutSettingsCardPadding.dp), contentAlignment = Alignment.CenterStart) {
                            Label(t(field.options.firstOrNull { it.id == value }?.label.orEmpty()), theme)
                        }
                        if (expanded && enabled) Popup(alignment = Alignment.TopStart, offset = IntOffset(0, popupOffset), onDismissRequest = { expanded = false }, properties = PopupProperties(focusable = true)) {
                            Column(Modifier.width(SyncWatchTokens.layoutSettingsInterfaceFieldWidth.dp).background(rgba(theme.surfaceRaised))) {
                                field.options.forEach { option ->
                                    Box(Modifier.fillMaxWidth().height(SyncWatchTokens.layoutSettingsControlHeight.dp)
                                        .clickable(role = Role.Button) { onEditorChange(editor.edit(field.id, option.id)); expanded = false }
                                        .padding(horizontal = SyncWatchTokens.layoutSettingsCardPadding.dp), contentAlignment = Alignment.CenterStart) { Label(t(option.label), theme) }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    val shape = RoundedCornerShape(SyncWatchTokens.controlCompactDialogRadius.dp)
    Column(Modifier.size(SyncWatchTokens.layoutSettingsWidth.dp, SyncWatchTokens.layoutPlayerSettingsHeight.dp).background(rgba(theme.surface), shape)
        .border(SyncWatchTokens.controlBorderWidth.dp, rgba(theme.border), shape).onPreviewKeyEvent {
            if (it.type == KeyEventType.KeyDown && it.key == Key.Escape) { close(); true } else false
        }) {
        Row(Modifier.fillMaxWidth().height(SyncWatchTokens.layoutSettingsHeaderHeight.dp).background(rgba(theme.backgroundDeep)).padding(horizontal = SyncWatchTokens.layoutSettingsCardPadding.dp), verticalAlignment = Alignment.CenterVertically) {
            Label(t("playerSettings"), theme, bold = true, modifier = Modifier.weight(1f).fillMaxHeight().pointerInput(density) {
                detectDragGestures { change, delta -> change.consume(); currentMove(delta / density.density) }
            })
            button("close") { close() }
        }
        Row(Modifier.weight(1f)) {
            Column(Modifier.width(SyncWatchTokens.layoutPlayerSettingsSidebarWidth.dp).fillMaxHeight().background(rgba(theme.backgroundDeep)).padding(SyncWatchTokens.layoutSettingsCardPadding.dp)) {
                SyncWatchPlayerSettings.sections.forEach { id ->
                    Box(Modifier.fillMaxWidth().height(SyncWatchTokens.layoutSettingsSidebarRowHeight.dp)
                        .background(rgba(if (section == id) theme.selection else theme.backgroundDeep), RoundedCornerShape(SyncWatchTokens.controlFieldRadius.dp))
                        .clickable(role = Role.Tab) { section = id }.semantics { selected = section == id }.padding(horizontal = SyncWatchTokens.layoutSettingsCardPadding.dp), contentAlignment = Alignment.CenterStart) { Label(t(id), theme) }
                }
            }
            Column(Modifier.weight(1f).fillMaxHeight().verticalScroll(rememberScrollState()).padding(SyncWatchTokens.layoutSettingsContentPadding.dp), verticalArrangement = Arrangement.spacedBy(SyncWatchTokens.controlCompactGap.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Label(t(section), theme, size = SyncWatchTokens.typeSettingsSectionSize, bold = true, modifier = Modifier.weight(1f))
                    button("resetSection", editor.canReset(section)) { onEditorChange(editor.reset(section)) }
                }
                Label(t(section + "Hint"), theme, muted = true)
                Column(Modifier.fillMaxWidth().border(SyncWatchTokens.controlBorderWidth.dp, rgba(theme.border), RoundedCornerShape(SyncWatchTokens.layoutPlayerSettingsCardRadius.dp))
                    .padding(SyncWatchTokens.layoutPlayerSettingsCardPadding.dp), verticalArrangement = Arrangement.spacedBy(SyncWatchTokens.controlCompactGap.dp)) {
                    SyncWatchPlayerSettings.fields.filter { it.section == section }.groupBy { it.row }.toSortedMap().values.forEach { fields ->
                        Row(horizontalArrangement = Arrangement.spacedBy(SyncWatchTokens.controlCompactGap.dp)) { fields.forEach { field(it, Modifier.weight(1f)) } }
                    }
                    if (section == "subtitles") PlayerSubtitlePreview(editor.values, language)
                }
            }
        }
        Row(Modifier.fillMaxWidth().height(SyncWatchTokens.layoutSettingsFooterHeight.dp).padding(horizontal = SyncWatchTokens.layoutSettingsCardPadding.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(SyncWatchTokens.controlCompactGap.dp)) {
            Label(t(if (editor.canSave) editor.message else "settingsReadOnly"), theme, muted = true, modifier = Modifier.weight(1f))
            button("cancel") { close() }
            button("save", editor.canSave, true) { onEditorChange(editor.save(onSave).first) }
        }
    }
}

@Composable fun PlayerSettingsGallery() {
    var section by remember { mutableStateOf("playback") }
    var state by remember { mutableStateOf(PlayerSettingsVisualState.editing) }
    var language by remember { mutableStateOf("en") }; var dark by remember { mutableStateOf(true) }; var fail by remember { mutableStateOf(false) }
    var editor by remember { mutableStateOf(PlayerSettingsEditor(editableFields = SyncWatchPlayerSettings.defaults.keys, canSave = true)) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    val theme = if (dark) SyncWatchTheme.dark else SyncWatchTheme.light
    Column(Modifier.fillMaxSize().background(rgba(theme.background))) {
        Row(Modifier.padding(SyncWatchTokens.controlCompactGap.dp), horizontalArrangement = Arrangement.spacedBy(SyncWatchTokens.controlCompactGap.dp)) {
            Action(section, true, theme) { section = SyncWatchPlayerSettings.sections[(SyncWatchPlayerSettings.sections.indexOf(section) + 1) % SyncWatchPlayerSettings.sections.size] }
            Action(state.name, true, theme) {
                state = PlayerSettingsVisualState.entries[(state.ordinal + 1) % PlayerSettingsVisualState.entries.size]
                editor = PlayerSettingsEditor(editableFields = SyncWatchPlayerSettings.defaults.keys, canSave = state != PlayerSettingsVisualState.readOnly, state = state)
            }
            Action(language, true, theme) { language = if (language == "en") "ru" else "en" }
            Action(if (dark) "dark" else "light", true, theme) { dark = !dark }
            Action("Fail save: $fail", true, theme) { fail = !fail }
        }
        BoxWithConstraints(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
            val maxX = ((maxWidth.value - SyncWatchTokens.layoutSettingsWidth) / 2).coerceAtLeast(0f)
            val maxY = ((maxHeight.value - SyncWatchTokens.layoutPlayerSettingsHeight) / 2).coerceAtLeast(0f)
            Box(Modifier.offset(offset.x.dp, offset.y.dp)) {
                key(section) { PlayerSettingsDialog(editor, { editor = it }, language, section, theme, onSave = { !fail }, onMove = {
                    offset = Offset((offset.x + it.x).coerceIn(-maxX, maxX), (offset.y + it.y).coerceIn(-maxY, maxY))
                }) }
            }
        }
    }
}
