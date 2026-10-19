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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.input.key.*
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// First-party source only; Compose/compiler/native/font/license build closure remains open.
enum class CallVisualState { idle, opening, webSurfaceReady, userActionRequired, failed, closed }
enum class CallPreviewState { cameraStarting, cameraActive, cameraDisabled, permissionDenied, deviceUnavailable }
data class CallRequest(val action: String, val values: List<Double> = emptyList())
data class CallPresentation(
    val state: CallVisualState = CallVisualState.idle,
    val preview: CallPreviewState = CallPreviewState.cameraDisabled,
    val joined: Boolean? = null, val microphoneEnabled: Boolean? = null, val cameraEnabled: Boolean? = null,
    val volume: Double? = null, val pinned: Boolean = false, val fullscreen: Boolean = false, val minimized: Boolean = false,
    val enabledActions: Set<String> = emptySet(),
) {
    val showsRemoteSurface get() = state == CallVisualState.webSurfaceReady || state == CallVisualState.userActionRequired
    val showsLocalPreview get() = state == CallVisualState.webSurfaceReady && joined == true && cameraEnabled == true && preview == CallPreviewState.cameraActive
    val displayedVolume get() = volume?.takeIf { it.isFinite() }?.coerceIn(0.0, 1.0) ?: 0.0
    fun previewLabel(hasSurface: Boolean): String = if (preview != CallPreviewState.cameraActive) preview.name else if (cameraEnabled == false) "cameraDisabled" else if (showsLocalPreview && hasSurface) "cameraActive" else "cameraStarting"
    fun allows(action: String): Boolean {
        if (action !in enabledActions || action !in SyncWatchCall.actions) return false
        if (action in setOf("setCallVolume", "setMicrophoneEnabled", "setCameraEnabled", "hangUp")) {
            if (state != CallVisualState.webSurfaceReady || joined != true) return false
            return when (action) {
                "setCallVolume" -> volume != null && volume.isFinite() && volume in 0.0..1.0
                "setMicrophoneEnabled" -> microphoneEnabled != null
                "setCameraEnabled" -> cameraEnabled != null
                else -> true
            }
        }
        return true
    }
    fun dispatch(request: CallRequest, handler: (CallRequest) -> Unit) {
        val v = request.values
        if (!allows(request.action) || v.any { !it.isFinite() }) return
        val valid = when (SyncWatchCall.actionKinds[request.action]) {
            "none" -> v.isEmpty()
            "boolean" -> v.size == 1 && (v[0] == 0.0 || v[0] == 1.0)
            "volume" -> v.size == 1 && v[0] in 0.0..1.0
            "delta" -> v.size == 2 && v.all { kotlin.math.abs(it) <= SyncWatchCall.maximumExtent }
            "size" -> v.size == 2 && v[0] >= SyncWatchTokens.layoutCallMinimumWidth && v[1] >= SyncWatchTokens.layoutCallMinimumHeight && v.all { it <= SyncWatchCall.maximumExtent }
            else -> false
        }
        if (valid) handler(request)
    }
    fun applyingFixture(request: CallRequest): CallPresentation = when (request.action) {
        "pin" -> copy(pinned = !pinned); "fullscreen" -> copy(fullscreen = !fullscreen)
        "minimize" -> copy(minimized = true); "restore" -> copy(minimized = false)
        "setCallVolume" -> copy(volume = request.values[0])
        "setMicrophoneEnabled" -> copy(microphoneEnabled = request.values[0] == 1.0)
        "setCameraEnabled" -> copy(cameraEnabled = request.values[0] == 1.0, preview = if (request.values[0] == 1.0) CallPreviewState.cameraActive else CallPreviewState.cameraDisabled)
        "close", "hangUp" -> copy(state = CallVisualState.closed, joined = false, preview = CallPreviewState.cameraDisabled)
        else -> this
    }
    companion object {
        fun gallery(item: CallGalleryCase): CallPresentation {
            val state = CallVisualState.valueOf(item.state); val preview = CallPreviewState.valueOf(item.preview)
            return CallPresentation(state, preview, state == CallVisualState.webSurfaceReady, true, preview != CallPreviewState.cameraDisabled, 0.7, enabledActions = SyncWatchCall.actions)
        }
    }
}

@Composable private fun CallIcon(name: String, theme: SyncWatchTheme, modifier: Modifier = Modifier, slash: Boolean = false, active: Boolean = false) {
    Canvas(modifier.size(SyncWatchTokens.layoutCallIconSize.dp)) {
        for (polygon in SyncWatchCall.icons[name].orEmpty() + (if (slash) SyncWatchCall.icons["slash"].orEmpty() else emptyList())) {
            val path = Path()
            for (i in polygon.indices step 2) {
                val x = polygon[i] / 20 * size.width; val y = polygon[i + 1] / 20 * size.height
                if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
            }
            path.close(); drawPath(path, rgba(if (active) SyncWatchTokens.colorDarkText else theme.text))
        }
    }
}
@Composable private fun CallAction(icon: String, label: String, enabled: Boolean, theme: SyncWatchTheme,
    small: Boolean = false, active: Boolean = false, slash: Boolean = false, destructive: Boolean = false, onAction: () -> Unit) {
    val size = if (small) SyncWatchTokens.layoutCallWindowButtonSize else SyncWatchTokens.layoutCallButtonSize
    Box(Modifier.size(size.dp).alpha(if (enabled) 1f else 0.4f)
        .background(rgba(if (destructive) SyncWatchTokens.colorSharedCallHangup else if (active) theme.accent else theme.surfaceRaised), CircleShape)
        .border(SyncWatchTokens.controlBorderWidth.dp, rgba(theme.border), CircleShape)
        .clickable(enabled = enabled, role = Role.Button, onClick = onAction).semantics { contentDescription = label }, contentAlignment = Alignment.Center) {
        CallIcon(icon, theme, slash = slash, active = active || destructive)
    }
}
@Composable private fun callGesture(label: String, enabled: Boolean, move: (Double, Double) -> Unit): Modifier {
    val current by rememberUpdatedState(move); val density = LocalDensity.current.density
    return Modifier.semantics {
        contentDescription = label
        if (!enabled) disabled()
        if (enabled) customActions = listOf(CustomAccessibilityAction(label) { current(10.0, 0.0); true })
    }.onKeyEvent {
        if (!enabled || it.type != KeyEventType.KeyDown) false else when (it.key) {
            Key.DirectionLeft -> { current(-10.0, 0.0); true }; Key.DirectionRight -> { current(10.0, 0.0); true }
            Key.DirectionUp -> { current(0.0, -10.0); true }; Key.DirectionDown -> { current(0.0, 10.0); true }
            else -> false
        }
    }.focusable(enabled).pointerInput(enabled, density) {
        if (enabled) awaitEachGesture {
            val down = awaitFirstDown(); var total = Offset.Zero
            val completed = drag(down.id) { change -> total += change.position - change.previousPosition; change.consume() }
            if (completed) current((total.x / density).toDouble(), (total.y / density).toDouble())
        }
    }
}

// Owned slots only. This renderer never starts browsers/devices or acknowledges media shutdown.
@Composable fun CallWindowShell(presentation: CallPresentation = CallPresentation(), language: String = "en",
    theme: SyncWatchTheme = SyncWatchTheme.dark, modifier: Modifier = Modifier,
    remoteSurface: (@Composable BoxScope.() -> Unit)? = null, localPreview: (@Composable BoxScope.() -> Unit)? = null,
    onAction: (CallRequest) -> Unit = {}) {
    fun t(key: String) = SyncWatchCopy.text(key, language)
    fun emit(action: String, values: List<Double> = emptyList()) = presentation.dispatch(CallRequest(action, values), onAction)
    @Composable fun button(action: String, icon: String, label: String, values: List<Double> = emptyList(), small: Boolean = false, active: Boolean = false, slash: Boolean = false) {
        CallAction(icon, t(label), presentation.allows(action), theme, small, active, slash, action == "hangUp") { emit(action, values) }
    }
    val radius = if (presentation.fullscreen) 0f else SyncWatchTokens.layoutCallRadius
    val gap = SyncWatchTokens.layoutCallGap.dp
    BoxWithConstraints(modifier.widthIn(min = SyncWatchTokens.layoutCallMinimumWidth.dp).heightIn(min = SyncWatchTokens.layoutCallMinimumHeight.dp)
        .clip(RoundedCornerShape(radius.dp)).background(rgba(theme.backgroundDeep)).border(SyncWatchTokens.controlBorderWidth.dp, rgba(theme.border), RoundedCornerShape(radius.dp))) {
        val width = maxWidth.value.toDouble(); val height = maxHeight.value.toDouble()
        Column(Modifier.fillMaxSize()) {
            Row(Modifier.fillMaxWidth().height(SyncWatchTokens.layoutCallHeaderHeight.dp).padding(horizontal = SyncWatchTokens.layoutCallInset.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(gap / 2)) {
                BasicText(t("callWindow"), Modifier.weight(1f).then(callGesture(t("moveCall"), presentation.allows("move")) { x, y -> emit("move", listOf(x, y)) }), style = TextStyle(color = rgba(theme.text), fontSize = SyncWatchTokens.typePlayerLabelSize.sp), maxLines = 1, overflow = TextOverflow.Ellipsis)
                button("pin", "pin", if (presentation.pinned) "unpinCall" else "pinCall", small = true, active = presentation.pinned)
                button(if (presentation.minimized) "restore" else "minimize", if (presentation.minimized) "restore" else "minimize", if (presentation.minimized) "restoreCall" else "minimizeCall", small = true)
                button("fullscreen", if (presentation.fullscreen) "restore" else "fullscreen", if (presentation.fullscreen) "exitFullscreenCall" else "fullscreenCall", small = true)
                button("close", "close", "closeCall", small = true)
            }
            Box(Modifier.weight(1f).fillMaxWidth().background(rgba(SyncWatchTokens.colorSharedVideoSurface)).clipToBounds().semantics { contentDescription = t("callSurface") }, contentAlignment = Alignment.Center) {
                if (presentation.showsRemoteSurface && remoteSurface != null) remoteSurface()
                else BasicText(t("callState" + presentation.state.name.replaceFirstChar { it.uppercase() }), style = TextStyle(color = rgba(SyncWatchTokens.colorDarkText), fontSize = SyncWatchTokens.typePlayerLabelSize.sp))
                Box(Modifier.align(Alignment.TopStart).padding(SyncWatchTokens.layoutCallInset.dp).size(SyncWatchTokens.layoutCallPreviewWidth.dp, SyncWatchTokens.layoutCallPreviewHeight.dp)
                    .clip(RoundedCornerShape(SyncWatchTokens.controlFieldRadius.dp)).background(rgba(theme.surfaceRaised)).border(SyncWatchTokens.controlBorderWidth.dp, rgba(theme.border), RoundedCornerShape(SyncWatchTokens.controlFieldRadius.dp))
                    .semantics { contentDescription = t(presentation.previewLabel(localPreview != null)) }, contentAlignment = Alignment.Center) {
                    if (presentation.showsLocalPreview && localPreview != null) localPreview()
                    else BasicText(t(presentation.previewLabel(localPreview != null)), Modifier.padding(2.dp), style = TextStyle(color = rgba(theme.textSecondary), fontSize = SyncWatchTokens.typeCaptionSize.sp, textAlign = androidx.compose.ui.text.style.TextAlign.Center))
                }
            }
            Row(Modifier.fillMaxWidth().height(SyncWatchTokens.layoutCallFooterHeight.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(gap, Alignment.CenterHorizontally)) {
                button("setMicrophoneEnabled", "microphone", if (presentation.microphoneEnabled == true) "microphoneOff" else "microphoneOn", listOf(if (presentation.microphoneEnabled == true) 0.0 else 1.0), active = presentation.microphoneEnabled == true, slash = presentation.microphoneEnabled == false)
                button("setCameraEnabled", "camera", if (presentation.cameraEnabled == true) "cameraOff" else "cameraOn", listOf(if (presentation.cameraEnabled == true) 0.0 else 1.0), active = presentation.cameraEnabled == true, slash = presentation.cameraEnabled == false)
                button("hangUp", "end", "hangUp")
                CallIcon(if (presentation.displayedVolume > 0) "volume" else "muted", theme)
                PlayerRange(presentation.displayedVolume, 1.0, t("callVolume"), presentation.allows("setCallVolume"), theme, Modifier.width(SyncWatchTokens.layoutCallVolumeWidth.dp), 0.05) { emit("setCallVolume", listOf(it)) }
            }
        }
        Box(Modifier.align(Alignment.BottomEnd).padding(2.dp).size(SyncWatchTokens.layoutCallResizeSize.dp)
            .then(callGesture(t("resizeCall"), presentation.allows("resize")) { x, y -> emit("resize", listOf((width + x).coerceIn(SyncWatchTokens.layoutCallMinimumWidth.toDouble(), SyncWatchCall.maximumExtent), (height + y).coerceIn(SyncWatchTokens.layoutCallMinimumHeight.toDouble(), SyncWatchCall.maximumExtent))) })) { CallIcon("resize", theme) }
    }
}

@Composable fun CallGallery() {
    var index by remember { mutableStateOf(2) }; var language by remember { mutableStateOf("en") }; var dark by remember { mutableStateOf(true) }
    var presentation by remember { mutableStateOf(CallPresentation.gallery(SyncWatchCall.galleryCases[index])) }; var last by remember { mutableStateOf("") }
    val theme = if (dark) SyncWatchTheme.dark else SyncWatchTheme.light
    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically), horizontalAlignment = Alignment.CenterHorizontally) {
        Row {
            Action(SyncWatchCall.galleryCases[index].id, true, theme) { index = (index + 1) % SyncWatchCall.galleryCases.size; presentation = CallPresentation.gallery(SyncWatchCall.galleryCases[index]) }
            Action(language, true, theme) { language = if (language == "en") "ru" else "en" }; Action(if (dark) "dark" else "light", true, theme) { dark = !dark }
        }
        CallWindowShell(presentation, language, theme, Modifier.size(SyncWatchTokens.layoutCallInitialWidth.dp, SyncWatchTokens.layoutCallInitialHeight.dp),
            remoteSurface = { Label(SyncWatchCopy.text("remoteFixture", language), theme.copy(text = SyncWatchTokens.colorDarkText)) },
            localPreview = { Box(Modifier.fillMaxSize().background(rgba(theme.accent)), contentAlignment = Alignment.Center) { Label(SyncWatchCopy.text("localFixture", language), theme.copy(text = SyncWatchTokens.colorDarkText), size = SyncWatchTokens.typeCaptionSize) } }) {
            last = it.action; presentation = presentation.applyingFixture(it)
        }
        Label(SyncWatchCopy.text("callFixture", language), theme, size = SyncWatchTokens.typeCaptionSize); Label(last, theme, size = SyncWatchTokens.typeCaptionSize)
    }
}
