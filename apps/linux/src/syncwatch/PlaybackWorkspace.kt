package syncwatch

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.*
import java.awt.EventQueue
import java.nio.file.Path
import java.util.concurrent.CompletableFuture
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import syncwatch.design.*
import syncwatch.domain.*
import syncwatch.playback.VLCPlayback
import syncwatch.playback.X11Display
import syncwatch.playback.X11VideoCanvas

/** Explicit development entry. Normal library and shared-watch activation have separate owners. */
internal data class LocalPlaybackLaunch(val file: Path, val packageDirectory: Path, val bridge: Path,
    val report: Path?, val detachProbe: Boolean) {
    fun initializeDisplay(): X11Display = VLCPlayback.initializeDisplay(bridge, packageDirectory)
    companion object {
        fun read(arguments: Array<String>): LocalPlaybackLaunch? {
            fun value(flag: String): String? = arguments.indexOf(flag).takeIf { it >= 0 }
                ?.let { arguments.getOrNull(it + 1) }
            if ("--local-playback" !in arguments) return null
            fun required(flag: String) = Path.of(requireNotNull(value(flag)) { flag }).toAbsolutePath().normalize()
            val report = value("--playback-report")?.let { Path.of(it).toAbsolutePath().normalize() }
            require(report == null || !java.nio.file.Files.exists(report)) { "playback-report-exists" }
            return LocalPlaybackLaunch(required("--local-playback"), required("--media-package"), required("--playback-bridge"),
                report, "--playback-detach-probe" in arguments)
        }
    }
}

/** Presentation/controller policy only; native commands stay on the playback worker. */
internal class PlaybackController(
    private val launch: LocalPlaybackLaunch,
    display: X11Display,
    parentScope: CoroutineScope,
) {
    private val ownerJob = SupervisorJob(parentScope.coroutineContext[Job])
    private val work = CoroutineScope(parentScope.coroutineContext + ownerJob)
    internal val player = VLCPlayback()
    internal val scope = PlaybackScope.fresh().replacingMedia()
    internal val loaded = CompletableDeferred<Unit>()
    internal val acceptanceRequested = launch.report != null
    private var started = false
    private var closing = false
    private var shutdown: CompletableFuture<Void>? = null
    val canvas = X11VideoCanvas(display, ::closeNative)
    var presentation by mutableStateOf(PlayerPresentation(title = launch.file.fileName?.toString().orEmpty(),
        enabledActions = setOf("endWatching", "toggleFullscreen")))
        private set
    var failed by mutableStateOf(false)
        private set

    fun start() {
        check(EventQueue.isDispatchThread())
        if (started || closing) return
        started = true
        work.launch {
            try {
                player.open(launch.bridge, launch.packageDirectory, canvas)
                player.load(launch.file, scope)
                loaded.complete(Unit)
                while (isActive && !closing) {
                    val value = player.observe(scope)
                    if (value.status == PlaybackStatus.failed) throw WatchFailure("media")
                    apply(value)
                    delay(100)
                }
            } catch (_: CancellationException) {
                loaded.completeExceptionally(CancellationException("closed"))
            } catch (error: Exception) {
                loaded.completeExceptionally(error)
                if (!closing) { failed = true; presentation = presentation.copy(enabledActions = setOf("endWatching")) }
            }
        }
    }

    private fun apply(value: PlaybackObservation) {
        val state = when {
            value.ended -> PlayerVisualState.ended
            value.buffering -> PlayerVisualState.buffering
            value.status != PlaybackStatus.ready -> PlayerVisualState.loading
            value.paused -> PlayerVisualState.paused
            else -> PlayerVisualState.playing
        }
        val enabled = mutableSetOf("endWatching", "toggleFullscreen", "playPause")
        if (value.seekable) enabled.addAll(setOf("seek", "skip"))
        if (value.volume != null) enabled.addAll(setOf("setMovieVolume", "muteMovie"))
        presentation = presentation.copy(state = state, positionMs = value.positionMs,
            durationMs = value.durationMs ?: 0, volume = value.volume ?: presentation.volume,
            muted = value.muted, enabledActions = enabled)
    }

    fun action(action: String, value: Double?, close: () -> Unit, fullscreen: () -> Unit) {
        if (closing) return
        presentation.dispatch(action, value) { accepted, number ->
            when (accepted) {
                "endWatching" -> requestClose(close)
                "toggleFullscreen" -> fullscreen()
                else -> work.launch {
                    try {
                        when (accepted) {
                            "playPause" -> player.setPaused(presentation.playing, scope)
                            "seek" -> if (number != null) player.seek(number.toLong(), scope)
                            "setMovieVolume" -> if (number != null) player.setVolume(number, presentation.muted, scope)
                            "muteMovie" -> player.setVolume(presentation.volume, !presentation.muted, scope)
                        }
                    } catch (_: Exception) { /* Rejection does not acknowledge a changed observation. */ }
                }
            }
        }
    }

    private fun closeNative(): CompletableFuture<Void> {
        check(EventQueue.isDispatchThread())
        shutdown?.let { return it.copy() }
        closing = true
        loaded.completeExceptionally(CancellationException("closed"))
        presentation = presentation.copy(enabledActions = emptySet())
        ownerJob.cancel()
        return player.closeAsync().also { shutdown = it }.copy()
    }

    fun requestClose(onClosed: () -> Unit) {
        val release = canvas.releaseAfter(closeNative())
        release.whenComplete { _, error -> EventQueue.invokeLater {
            if (error == null) onClosed() else failed = true
        } }
    }
}

@Composable internal fun PlaybackWorkspace(controller: PlaybackController, onClose: () -> Unit, onFullscreen: () -> Unit) {
    val preferences = remember { AppearancePreferences(FileLocalStateStore(AppearancePreferences.defaultPath())) }
    val language = preferences.state.preferences.language
    val dark = when (preferences.state.preferences.theme) { "dark" -> true; "light" -> false; else -> isSystemInDarkTheme() }
    val theme = if (dark) SyncWatchTheme.dark else SyncWatchTheme.light
    LaunchedEffect(controller) { controller.start() }
    PlayerChrome(controller.presentation, language, theme,
        videoSurface = { NativePlayerSurface(controller.canvas) },
        onAction = { action, value -> controller.action(action, value, onClose, onFullscreen) })
    LaunchedEffect(controller.failed) {
        if (controller.failed && !controller.acceptanceRequested) javax.swing.JOptionPane.showMessageDialog(null,
            SyncWatchCopy.text("playbackFailed", language), "SyncWatch", javax.swing.JOptionPane.ERROR_MESSAGE)
    }
}
