// SPDX-License-Identifier: Apache-2.0
package syncwatch.design

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.drag
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.input.key.*
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.foundation.text.BasicText
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.round

// First-party source only. Compose/compiler/native/font/license build prerequisites remain open.
enum class PlayerVisualState { loading, paused, playing, buffering, fullscreen, connectionInterrupted, ended }
data class PlayerPresentation(
    val state: PlayerVisualState = PlayerVisualState.loading,
    val title: String = "",
    val positionMs: Long = 0,
    val durationMs: Long = 0,
    val volume: Double = 1.0,
    val muted: Boolean = false,
    val skipSeconds: Int = 10,
    val hasPrevious: Boolean = false,
    val hasNext: Boolean = false,
    val enabledActions: Set<String> = emptySet(),
) {
    val isValid: Boolean get() = durationMs in 0..SyncWatchPlayer.maximumPositionMs && positionMs in 0..durationMs.coerceAtLeast(0) && volume.isFinite() && volume in 0.0..1.0 && skipSeconds in 1..600
    val playing: Boolean get() = state == PlayerVisualState.playing || state == PlayerVisualState.fullscreen
    val displayedDuration: Double get() = durationMs.coerceIn(0, SyncWatchPlayer.maximumPositionMs).toDouble()
    val displayedPosition: Double get() = positionMs.coerceAtLeast(0).toDouble().coerceAtMost(displayedDuration)
    fun allows(action: String): Boolean = action in enabledActions && action in SyncWatchPlayer.actions && when (action) {
        "playPause", "seek", "skip", "previousFile", "nextFile" -> isValid && state in setOf(PlayerVisualState.paused, PlayerVisualState.playing, PlayerVisualState.fullscreen) && when (action) {
            "seek", "skip" -> durationMs > 0
            "previousFile" -> hasPrevious
            "nextFile" -> hasNext
            else -> true
        }
        "setMovieVolume", "muteMovie" -> isValid
        else -> true
    }
    fun dispatch(action: String, value: Double? = null, handler: (String, Double?) -> Unit) {
        if (!allows(action)) return
        when (action) {
            "seek" -> if (value == null || !value.isFinite() || round(value) != value || value !in 0.0..durationMs.toDouble()) return
            "skip" -> {
                if (value !in listOf(-1.0, 1.0) || !allows("seek")) return
                val target = (positionMs + value!! * skipSeconds * 1000).coerceIn(0.0, durationMs.toDouble())
                if (target != positionMs.toDouble()) handler("seek", target)
                return
            }
            "setMovieVolume" -> if (value == null || !value.isFinite() || value !in 0.0..1.0) return
            else -> if (value != null) return
        }
        handler(action, value)
    }
    companion object {
        fun time(milliseconds: Double): String {
            val seconds = (if (milliseconds.isFinite()) milliseconds else 0.0).coerceIn(0.0, SyncWatchPlayer.maximumPositionMs.toDouble()).toLong() / 1000
            fun pad(n: Long) = n.toString().padStart(2, '0')
            return if (seconds >= 3600) "${seconds / 3600}:${pad(seconds / 60 % 60)}:${pad(seconds % 60)}" else "${pad(seconds / 60)}:${pad(seconds % 60)}"
        }
        fun gallery(state: PlayerVisualState) = PlayerPresentation(state = state, title = SyncWatchCopy.galleryMovies[1],
            durationMs = if (state == PlayerVisualState.loading) 0 else 5400000,
            positionMs = if (state == PlayerVisualState.loading) 0 else if (state == PlayerVisualState.ended) 5400000 else 754000,
            volume = 0.7, hasPrevious = true, hasNext = true, enabledActions = SyncWatchPlayer.actions)
    }
}

@Composable private fun PlayerAction(icon: String, label: String, enabled: Boolean, theme: SyncWatchTheme,
    prominent: Boolean = false, onAction: () -> Unit) {
    val width = if (prominent) SyncWatchTokens.controlPlayerProminentSize else SyncWatchTokens.controlPlayerButtonSize
    Box(Modifier.size(width.dp).alpha(if (enabled) 1f else 0.4f)
        .background(rgba(if (prominent) theme.accent else theme.surfaceRaised), CircleShape)
        .border(SyncWatchTokens.controlBorderWidth.dp, rgba(theme.border), CircleShape)
        .clickable(enabled = enabled, role = Role.Button, onClick = onAction).semantics { contentDescription = label },
        contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(SyncWatchTokens.controlPlayerIconSize.dp)) {
            for (polygon in SyncWatchPlayer.icons[icon].orEmpty()) {
                val path = Path()
                for (i in polygon.indices step 2) {
                    val x = polygon[i] / 20 * size.width; val y = polygon[i + 1] / 20 * size.height
                    if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
                }
                path.close(); drawPath(path, rgba(if (prominent) SyncWatchTokens.colorDarkText else theme.text))
            }
        }
    }
}

@Composable private fun PlayerRange(value: Double, maximum: Double, label: String, enabled: Boolean,
    theme: SyncWatchTheme, modifier: Modifier, step: Double, onChange: (Double) -> Unit) {
    val current by rememberUpdatedState(value)
    val currentChange by rememberUpdatedState(onChange)
    val safeMaximum = maximum.coerceAtLeast(1.0)
    Canvas(modifier.height(SyncWatchTokens.controlPlayerSliderHeight.dp).alpha(if (enabled) 1f else 0.4f)
        .semantics {
            contentDescription = label
            progressBarRangeInfo = ProgressBarRangeInfo(value.toFloat(), 0f..safeMaximum.toFloat())
            if (!enabled) disabled()
            setProgress { requested -> if (enabled) { currentChange(requested.toDouble().coerceIn(0.0, safeMaximum)); true } else false }
        }
        .onKeyEvent {
            if (!enabled || it.type != KeyEventType.KeyDown) false else when (it.key) {
                Key.DirectionLeft, Key.DirectionDown -> { currentChange((current - step).coerceAtLeast(0.0)); true }
                Key.DirectionRight, Key.DirectionUp -> { currentChange((current + step).coerceAtMost(safeMaximum)); true }
                Key.MoveHome -> { currentChange(0.0); true }
                Key.MoveEnd -> { currentChange(safeMaximum); true }
                else -> false
            }
        }.focusable(enabled)
        .pointerInput(enabled, safeMaximum) {
            if (enabled) awaitEachGesture {
                fun update(x: Float) { currentChange((x / size.width.coerceAtLeast(1) * safeMaximum).coerceIn(0.0, safeMaximum)) }
                val down = awaitFirstDown(); down.consume(); update(down.position.x)
                drag(down.id) { change -> change.consume(); update(change.position.x) }
            }
        }) {
        val fraction = (value / safeMaximum).toFloat().coerceIn(0f, 1f)
        val y = size.height / 2
        drawLine(rgba(theme.border), Offset(0f, y), Offset(size.width, y), SyncWatchTokens.controlSliderTrackHeight.dp.toPx())
        drawLine(rgba(theme.accent), Offset(0f, y), Offset(size.width * fraction, y), SyncWatchTokens.controlSliderTrackHeight.dp.toPx())
        drawCircle(rgba(theme.accent), SyncWatchTokens.controlSliderThumbRadius.dp.toPx(), Offset(size.width * fraction, y))
    }
}

@Composable fun PlayerChrome(presentation: PlayerPresentation = PlayerPresentation(), language: String = "en",
    theme: SyncWatchTheme = SyncWatchTheme.dark, modifier: Modifier = Modifier,
    videoSurface: @Composable BoxScope.() -> Unit = {}, onAction: (String, Double?) -> Unit = { _, _ -> }) {
    fun t(key: String) = SyncWatchCopy.text(key, language)
    fun emit(action: String, value: Double? = null) = presentation.dispatch(action, value, onAction)
    @Composable fun button(action: String, icon: String, label: String = action, value: Double? = null, prominent: Boolean = false) {
        PlayerAction(icon, t(label), presentation.allows(action), theme, prominent) { emit(action, value) }
    }
    val gap = SyncWatchTokens.controlCompactGap.dp
    Column(modifier.widthIn(min = SyncWatchTokens.layoutMinimumWidth.dp).heightIn(min = SyncWatchTokens.layoutMinimumHeight.dp)) {
        Row(Modifier.fillMaxWidth().height(SyncWatchTokens.layoutPlayerToolbarHeight.dp).background(rgba(theme.backgroundDeep))
            .padding(horizontal = SyncWatchTokens.layoutPanelPadding.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(gap)) {
            button("showLibrary", "library")
            BasicText(presentation.title, Modifier.weight(1f), style = TextStyle(color = rgba(theme.text), fontSize = SyncWatchTokens.typePlayerLabelSize.sp), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Label(t(presentation.state.name), theme, muted = true, size = SyncWatchTokens.typePlayerLabelSize)
            button("openCall", "call"); button("toggleFullscreen", "fullscreen"); button("endWatching", "end")
        }
        Box(Modifier.weight(1f).fillMaxWidth().background(rgba(SyncWatchTokens.colorSharedVideoSurface)).clipToBounds()
            .semantics { contentDescription = t("videoSurface") }, contentAlignment = Alignment.Center, content = videoSurface)
        Column(Modifier.fillMaxWidth().height(SyncWatchTokens.layoutPlayerFooterHeight.dp).background(rgba(theme.backgroundDeep))
            .padding(horizontal = SyncWatchTokens.layoutPanelPadding.dp)) {
            Row(Modifier.fillMaxWidth().height(SyncWatchTokens.controlPlayerSliderHeight.dp), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(gap)) {
                Label(PlayerPresentation.time(presentation.displayedPosition), theme, size = SyncWatchTokens.typePlayerLabelSize, modifier = Modifier.width(SyncWatchTokens.layoutPlayerTimeWidth.dp))
                PlayerRange(presentation.displayedPosition, presentation.displayedDuration, t("seek"), presentation.allows("seek"), theme, Modifier.weight(1f), 1000.0) { emit("seek", round(it)) }
                Label(PlayerPresentation.time(presentation.displayedDuration), theme, size = SyncWatchTokens.typePlayerLabelSize, modifier = Modifier.width(SyncWatchTokens.layoutPlayerTimeWidth.dp))
            }
            Row(Modifier.weight(1f).fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(gap)) { button("openPlayerSettings", "settings", "playerSettings"); button("openPlaylist", "playlist", "playlist") }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(gap)) {
                    button("previousFile", "previous"); button("skip", "backward", "skipBackward", -1.0)
                    button("playPause", if (presentation.playing) "pause" else "play", if (presentation.playing) "pause" else "play", prominent = true)
                    button("skip", "forward", "skipForward", 1.0); button("nextFile", "next")
                }
                Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(gap, Alignment.End)) {
                    button("selectSubtitles", "subtitles", "subtitles"); button("selectAudio", "audio", "audioTracks")
                    button("muteMovie", if (presentation.muted) "muted" else "volume", if (presentation.muted) "unmuteMovie" else "muteMovie")
                    PlayerRange(if (presentation.isValid) presentation.volume else 0.0, 1.0, t("setMovieVolume"), presentation.allows("setMovieVolume"), theme, Modifier.width(SyncWatchTokens.layoutPlayerVolumeWidth.dp), 0.05) { emit("setMovieVolume", it) }
                }
            }
        }
    }
}

@Composable fun PlayerGallery() {
    var presentation by remember { mutableStateOf(PlayerPresentation.gallery(PlayerVisualState.paused)) }
    var language by remember { mutableStateOf("en") }
    var dark by remember { mutableStateOf(true) }
    var last by remember { mutableStateOf("") }
    val theme = if (dark) SyncWatchTheme.dark else SyncWatchTheme.light
    Column {
        Row(horizontalArrangement = Arrangement.spacedBy(SyncWatchTokens.controlCompactGap.dp)) {
            Action(presentation.state.name, true, theme) { presentation = PlayerPresentation.gallery(PlayerVisualState.entries[(presentation.state.ordinal + 1) % PlayerVisualState.entries.size]) }
            Action(language, true, theme) { language = if (language == "en") "ru" else "en" }
            Action(if (dark) "dark" else "light", true, theme) { dark = !dark }
            Label(last, theme)
        }
        PlayerChrome(presentation, language, theme, Modifier.weight(1f), videoSurface = {
            Label(SyncWatchCopy.text("playerFixture", language), theme.copy(text = SyncWatchTokens.colorDarkText))
        }) { action, value ->
            last = "$action: $value"
            presentation = when (action) {
                "seek" -> presentation.copy(positionMs = value!!.toLong())
                "playPause" -> presentation.copy(state = if (presentation.playing) PlayerVisualState.paused else PlayerVisualState.playing)
                "setMovieVolume" -> presentation.copy(volume = value!!)
                "muteMovie" -> presentation.copy(muted = !presentation.muted)
                else -> presentation
            }
        }
    }
}
