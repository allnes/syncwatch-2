package syncwatch

import androidx.compose.ui.awt.ComposeWindow
import androidx.compose.ui.window.WindowPlacement
import androidx.compose.ui.window.WindowState
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardOpenOption
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeout
import syncwatch.design.PlayerPresentation
import syncwatch.design.PlayerVisualState
import syncwatch.domain.PlaybackObservation
import syncwatch.domain.PlaybackStatus
import syncwatch.ipc.Json

/** Explicit native application acceptance. No synthetic desktop input or visual-parity claim. */
internal object PlaybackAcceptance {
    suspend fun run(controller: PlaybackController, window: ComposeWindow, state: WindowState,
        report: Path, detach: Boolean, exit: () -> Unit) {
        val result = linkedMapOf<String, Any>("success" to false, "guiObserved" to false,
            "physicalOutputAccepted" to false, "applicationBuildReady" to false)
        var stage = "load"
        suspend fun observed(condition: (PlaybackObservation) -> Boolean): PlaybackObservation = withTimeout(15_000) {
            var value = controller.player.observe(controller.scope)
            while (true) {
                check(value.status != PlaybackStatus.failed && !value.ended) { "native-state" }
                if (condition(value)) return@withTimeout value
                delay(20); value = controller.player.observe(controller.scope)
            }
            @Suppress("UNREACHABLE_CODE") error("native-transition")
        }
        suspend fun presented(condition: (PlayerPresentation) -> Boolean) = withTimeout(15_000) {
            while (!condition(controller.presentation)) { check(!controller.failed); delay(20) }
        }
        fun fullscreen() {
            state.placement = if (state.placement == WindowPlacement.Fullscreen) WindowPlacement.Floating else WindowPlacement.Fullscreen
        }
        fun action(name: String, value: Double? = null) = controller.action(name, value, {}, ::fullscreen)
        try {
            withTimeout(20_000) { controller.loaded.await() }
            val initial = observed { it.status == PlaybackStatus.ready && it.paused && it.seekable }
            check(initial.durationMs == 4000L && initial.positionMs < 300)
            presented { it.state == PlayerVisualState.paused }
            stage = "play-pause"
            action("playPause")
            observed { !it.paused && it.positionMs >= 450 && it.videoOutputs == 1 && it.width == 320 && it.height == 180 }
            presented { it.playing }
            action("playPause")
            val paused = observed { it.paused }
            delay(250)
            check(kotlin.math.abs(controller.player.observe(controller.scope).positionMs - paused.positionMs) <= 60)
            presented { it.state == PlayerVisualState.paused }
            stage = "seek"
            action("seek", 2500.0); observed { it.paused && it.positionMs in 2300..2700 }
            action("seek", 250.0); observed { it.paused && it.positionMs <= 650 }
            stage = "volume"
            presented { it.allows("setMovieVolume") }
            action("setMovieVolume", .5); observed { it.volume == .5 }
            presented { it.volume == .5 }
            action("muteMovie"); observed { it.muted }
            result["actualNativeSurface"] = true
            result["nativeControlsPassed"] = true
            stage = "resize"
            val width = controller.canvas.width
            result["initialWindowWidth"] = window.width
            result["initialCanvasWidth"] = width
            // Resize the real window inward so small remote desktops cannot
            // clamp both the original and requested size to the same bounds.
            state.placement = WindowPlacement.Floating
            window.setSize((window.width * .8).toInt(), (window.height * .8).toInt())
            withTimeout(15_000) { while (controller.canvas.width == width) delay(20) }
            observed { it.paused && it.videoOutputs == 1 }
            result["nativeResizeChecked"] = true
            stage = "display-output"
            val output = window.graphicsConfiguration.bounds
            result["displayBounds"] = output.toString()
            check(output.width > 0 && output.height > 0) { "display-no-active-output" }
            stage = "fullscreen"
            action("toggleFullscreen")
            withTimeout(15_000) { while (window.placement != WindowPlacement.Fullscreen || window.bounds != window.graphicsConfiguration.bounds) delay(20) }
            observed { it.paused && it.videoOutputs == 1 }
            action("toggleFullscreen")
            withTimeout(15_000) { while (window.placement != WindowPlacement.Floating) delay(20) }
            observed { it.paused && it.videoOutputs == 1 }
            check(controller.canvas.isDisplayable)
            if (detach) {
                stage = "detach"
                val parent = requireNotNull(controller.canvas.parent)
                parent.remove(controller.canvas); parent.validate()
                check(!controller.canvas.isDisplayable)
            }
            result["nativeFullscreenChecked"] = true
            result["detachRequested"] = detach
            result["success"] = true
        } catch (error: Exception) {
            result["failure"] = stage
            result["error"] = error.javaClass.simpleName
            error.message?.takeIf { it == "display-no-active-output" }?.let { result["reason"] = it }
        } finally {
            controller.requestClose {
                result["nativeReleasedBeforeWindowDisposal"] = window.isDisplayable
                result["finalWindowWidth"] = window.width
                result["finalCanvasWidth"] = controller.canvas.width
                result["finalPlacement"] = window.placement.name
                try {
                    Files.createDirectories(report.parent)
                    Files.writeString(report, Json.write(result) + "\n", StandardOpenOption.CREATE_NEW)
                } finally { exit() }
            }
        }
    }
}
