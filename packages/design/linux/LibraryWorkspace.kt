// SPDX-License-Identifier: Apache-2.0
package syncwatch.design

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// Source-only renderer until the pinned Compose/compiler/native graph is buildable.
// Foundation primitives deliberately avoid an additional Material theme dependency.
enum class LibraryVisualState { empty, scanning, selected, missingMedia, reconnecting }
data class LibraryEntry(val id: String, val title: String, val location: String)
data class LibraryPresentation(
    val state: LibraryVisualState = LibraryVisualState.empty,
    val entries: List<LibraryEntry> = emptyList(),
    val selectedID: String? = null,
    val enabledActions: Set<String> = emptySet(),
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

// Generated data is RRGGBBAA, while Compose's packed integer constructor is ARGB.
private fun rgba(value: Long) = Color(
    ((value shr 24) and 255).toFloat() / 255,
    ((value shr 16) and 255).toFloat() / 255,
    ((value shr 8) and 255).toFloat() / 255,
    (value and 255).toFloat() / 255,
)
private val gap get() = SyncWatchTokens.layoutPanelGap.dp

@Composable private fun Label(text: String, theme: SyncWatchTheme, muted: Boolean = false,
    size: Float = SyncWatchTokens.typeBodySize, bold: Boolean = false, modifier: Modifier = Modifier) {
    BasicText(text, modifier, style = TextStyle(color = rgba(if (muted) theme.textSecondary else theme.text),
        fontSize = size.sp, fontWeight = if (bold) FontWeight.Bold else FontWeight.Normal))
}
@Composable private fun Panel(theme: SyncWatchTheme, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    val shape = RoundedCornerShape(SyncWatchTokens.layoutPanelRadius.dp)
    Column(modifier.background(rgba(theme.surface), shape).border(SyncWatchTokens.controlBorderWidth.dp, rgba(theme.border), shape)
        .padding(SyncWatchTokens.layoutPanelPadding.dp), content = content)
}
@Composable private fun Action(text: String, enabled: Boolean, theme: SyncWatchTheme, filled: Boolean = false,
    onClick: () -> Unit) {
    val shape = RoundedCornerShape(SyncWatchTokens.controlButtonRadius.dp)
    Box(Modifier.alpha(if (enabled) 1f else 0.4f)
        .background(rgba(if (filled) theme.accent else theme.surfaceRaised), shape)
        .border(SyncWatchTokens.controlBorderWidth.dp, rgba(if (filled) theme.accent else theme.border), shape)
        .clickable(enabled = enabled, role = Role.Button, onClick = onClick)
        .heightIn(min = (if (filled) SyncWatchTokens.controlFilledButtonMinHeight else SyncWatchTokens.controlOutlinedButtonMinHeight).dp)
        .padding(horizontal = SyncWatchTokens.layoutPanelPadding.dp), contentAlignment = Alignment.Center) {
        Label(text, if (filled) theme.copy(text = SyncWatchTokens.colorDarkText) else theme, bold = true)
    }
}

@Composable fun LibraryWorkspace(presentation: LibraryPresentation = LibraryPresentation(), language: String = "en",
    theme: SyncWatchTheme = SyncWatchTheme.dark, modifier: Modifier = Modifier,
    onAction: (String, String?) -> Unit = { _, _ -> }) {
    var query by remember { mutableStateOf("") }
    fun text(key: String) = SyncWatchCopy.text(key, language)
    fun emit(action: String, value: String? = null) = presentation.dispatch(action, value, onAction)
    @Composable fun button(action: String, filled: Boolean = false) {
        Action(text(action), presentation.allows(action), theme, filled) { emit(action) }
    }
    Column(modifier.widthIn(min = SyncWatchTokens.layoutMinimumWidth.dp).heightIn(min = SyncWatchTokens.layoutMinimumHeight.dp)
        .background(Brush.linearGradient(listOf(rgba(theme.gradientStart), rgba(theme.background), rgba(theme.backgroundDeep))))
        .padding(SyncWatchTokens.layoutWorkspacePadding.dp), verticalArrangement = Arrangement.spacedBy(gap)) {
        Panel(theme, Modifier.fillMaxWidth().height(SyncWatchTokens.layoutHeaderHeight.dp)) {
            Row(Modifier.fillMaxSize(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(gap)) {
                Box(Modifier.size(SyncWatchTokens.controlBrandSize.dp).background(rgba(theme.accent), RoundedCornerShape(SyncWatchTokens.controlButtonRadius.dp)), contentAlignment = Alignment.Center) {
                    Canvas(Modifier.size(SyncWatchTokens.controlIconSize.dp)) {
                        val path = Path().apply { moveTo(size.width * .25f, size.height * .15f); lineTo(size.width * .85f, size.height * .5f); lineTo(size.width * .25f, size.height * .85f); close() }
                        drawPath(path, rgba(SyncWatchTokens.colorDarkText))
                    }
                }
                Label(text("brand"), theme, size = SyncWatchTokens.typeBrandSize, bold = true)
                Label(text("room"), theme, modifier = Modifier.weight(1f))
                button("openSettings")
            }
        }
        Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(gap)) {
            Panel(theme, Modifier.width(SyncWatchTokens.layoutLibraryPanelWidth.dp).fillMaxHeight()) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Label(text("library"), theme, size = SyncWatchTokens.typeSectionSize, bold = true)
                    Label("${presentation.entries.size} ${text("files")}", theme, muted = true)
                }
                Spacer(Modifier.height(gap))
                Row(horizontalArrangement = Arrangement.spacedBy(SyncWatchTokens.controlCompactGap.dp)) { button("chooseFolder"); button("rescan") }
                Spacer(Modifier.height(gap))
                BasicTextField(query, { query = it; emit("search", it) }, enabled = presentation.allows("search"), singleLine = true,
                    textStyle = TextStyle(color = rgba(theme.text), fontSize = SyncWatchTokens.typeBodySize.sp),
                    modifier = Modifier.fillMaxWidth().height(SyncWatchTokens.controlFieldHeight.dp)
                        .background(rgba(theme.inputFill), RoundedCornerShape(SyncWatchTokens.controlFieldRadius.dp))
                        .border(SyncWatchTokens.controlBorderWidth.dp, rgba(theme.border), RoundedCornerShape(SyncWatchTokens.controlFieldRadius.dp))
                        .semantics { contentDescription = text("search") },
                    decorationBox = { inner -> Box(Modifier.padding(horizontal = SyncWatchTokens.layoutPanelPadding.dp), contentAlignment = Alignment.CenterStart) {
                        if (query.isEmpty()) Label(text("search"), theme, muted = true)
                        inner()
                    } })
                Spacer(Modifier.height(gap))
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(SyncWatchTokens.controlCompactGap.dp)) {
                    if (presentation.entries.isEmpty()) Label(text(if (presentation.state == LibraryVisualState.scanning) "scanning" else "empty"), theme, muted = true)
                    presentation.entries.filter { query.isEmpty() || it.title.contains(query, ignoreCase = true) }.forEach { entry ->
                        val shape = RoundedCornerShape(SyncWatchTokens.controlRowRadius.dp)
                        Box(Modifier.fillMaxWidth().heightIn(min = SyncWatchTokens.controlRowMinHeight.dp)
                            .background(rgba(if (entry.id == presentation.selectedID) theme.selection else theme.surfaceRaised), shape)
                            .semantics { selected = entry.id == presentation.selectedID }
                            .clickable(enabled = presentation.allows("selectMovie"), role = Role.Button) { emit("selectMovie", entry.id) }
                            .padding(SyncWatchTokens.layoutPanelPadding.dp)) { Label(entry.title, theme) }
                    }
                }
            }
            BoxWithConstraints(Modifier.weight(1f).fillMaxHeight()) {
                val detailHeight = (maxHeight - SyncWatchTokens.layoutLowerPanelMinHeight.dp - gap)
                    .coerceIn(SyncWatchTokens.layoutSelectedPanelMinHeight.dp, SyncWatchTokens.layoutSelectedPanelMaxHeight.dp)
                Column(verticalArrangement = Arrangement.spacedBy(gap)) {
                    Panel(theme, Modifier.fillMaxWidth().height(detailHeight)) {
                        val entry = presentation.selected
                        if (entry == null) Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Label(text("selectMovie"), theme, muted = true) }
                        else Column(Modifier.verticalScroll(rememberScrollState()).padding((SyncWatchTokens.layoutDetailPadding - SyncWatchTokens.layoutPanelPadding).dp), verticalArrangement = Arrangement.spacedBy(gap)) {
                            Label(text("selectedMovie"), theme, muted = true)
                            Label(entry.title, theme, size = SyncWatchTokens.typeTitleSize, bold = true)
                            val metricColumns = if (maxWidth >= (500 + SyncWatchTokens.layoutDetailPadding * 2).dp) 4 else 2
                            listOf("duration", "resolution", "audio", "subtitles").chunked(metricColumns).forEach { group ->
                                Row { group.forEach { key -> Column(Modifier.weight(1f)) {
                                    Label(text(key), theme, muted = true); Label(text("unknown"), theme, bold = true)
                                } } }
                            }
                            if (presentation.state == LibraryVisualState.missingMedia) Label(text("missingMedia"), theme, muted = true)
                            // Vertical action group keeps long translations usable at the minimum viewport.
                            Column(verticalArrangement = Arrangement.spacedBy(SyncWatchTokens.controlCompactGap.dp)) { button("startWatching", true); button("continueWatching"); button("endWatching") }
                            Label(text("fileLocation"), theme); Label(entry.location, theme, muted = true)
                        }
                    }
                    Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(gap)) {
                        Panel(theme, Modifier.weight(1f).fillMaxHeight()) {
                            Label(text("roomStatus"), theme, size = SyncWatchTokens.typeSectionSize, bold = true)
                            Spacer(Modifier.height(gap)); Label(text(if (presentation.state == LibraryVisualState.reconnecting) "reconnecting" else "disconnected"), theme, muted = true)
                            Spacer(Modifier.weight(1f)); button("openCall")
                        }
                        Panel(theme, Modifier.weight(1f).fillMaxHeight()) {
                            Label(text("recentActivity"), theme, size = SyncWatchTokens.typeSectionSize, bold = true)
                            Spacer(Modifier.height(gap)); Label(text("noActivity"), theme, muted = true)
                        }
                    }
                }
            }
        }
    }
}

@Composable fun DesignGallery() {
    var state by remember { mutableStateOf(LibraryVisualState.selected) }
    var language by remember { mutableStateOf("en") }
    var dark by remember { mutableStateOf(true) }
    var selectedID by remember { mutableStateOf<String?>(null) }
    var lastAction by remember { mutableStateOf("") }
    val theme = if (dark) SyncWatchTheme.dark else SyncWatchTheme.light
    Column {
        Row(Modifier.padding(SyncWatchTokens.layoutPanelPadding.dp), horizontalArrangement = Arrangement.spacedBy(SyncWatchTokens.controlCompactGap.dp)) {
            Action(state.name, true, theme) { state = LibraryVisualState.entries[(state.ordinal + 1) % LibraryVisualState.entries.size] }
            Action(language, true, theme) { language = if (language == "en") "ru" else "en" }
            Action(if (dark) "dark" else "light", true, theme) { dark = !dark }
            Label(lastAction, theme)
        }
        val fixture = LibraryPresentation.gallery(state)
        LibraryWorkspace(fixture.copy(selectedID = selectedID ?: fixture.selectedID), language, theme, Modifier.weight(1f)) { action, value ->
            lastAction = action
            if (action == "selectMovie") selectedID = value
        }
    }
}
