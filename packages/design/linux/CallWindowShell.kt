// SPDX-License-Identifier: Apache-2.0
package syncwatch.design

import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.ui.Modifier

// Source only until Linux dependency/compiler/native/license closure.
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

// Owned observations and content only; the shared document owns composition.
@Composable fun CallWindowShell(presentation: CallPresentation = CallPresentation(), language: String = "en",
    theme: SyncWatchTheme = SyncWatchTheme.dark, modifier: Modifier = Modifier,
    remoteSurface: (@Composable BoxScope.() -> Unit)? = null, localPreview: (@Composable BoxScope.() -> Unit)? = null,
    onAction: (CallRequest) -> Unit = {}) {
    val slots = mutableMapOf<String, @Composable BoxScope.() -> Unit>()
    if (presentation.showsRemoteSurface && remoteSurface != null) slots["remoteCallSurface"] = remoteSurface
    if (presentation.showsLocalPreview && localPreview != null) slots["localCameraPreview"] = localPreview
    DesignSurface("Call", DesignBindings.call(presentation, remoteSurface != null, localPreview != null), language, theme, modifier, slots) { event ->
        val values = event.value?.split(',')?.map { it.toDoubleOrNull() ?: Double.NaN } ?: emptyList()
        presentation.dispatch(CallRequest(event.action, values), onAction)
    }
}
