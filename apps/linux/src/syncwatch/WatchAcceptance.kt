package syncwatch

import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardOpenOption
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.async
import kotlinx.coroutines.cancel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.CancellationException
import syncwatch.domain.PlaybackStatus
import syncwatch.domain.WatchPhase
import syncwatch.ipc.Json

/** Explicit own-application integration check. Manual and physical acceptance stay separate. */
internal object WatchAcceptance {
    fun requested(arguments: Array<String>) = "--watch-check-report" in arguments
    private suspend fun until(condition: suspend () -> Boolean) = withTimeout(20_000) {
        while (!condition()) delay(40)
    }
    suspend fun run(arguments: Array<String>, workspace: ApplicationSession, exit: () -> Unit) {
        if (!requested(arguments)) return
        fun value(flag: String) = arguments.indexOf(flag).takeIf { it >= 0 }?.let { arguments.getOrNull(it + 1) }
        val report = value("--watch-check-report")?.let(Path::of)
        val file = value("--watch-check-media")?.let(Path::of)
        val mode = value("--watch-check-mode") ?: "normal"
        if (report == null || file == null || value("--state-directory") == null || Files.exists(report)) { exit(); return }
        val result = linkedMapOf<String, Any>("success" to false, "guiObserved" to false,
            "physicalOutputAccepted" to false, "applicationBuildReady" to false)
        val watch = workspace.watch; val catalog = workspace.library; val preferences = workspace.preferences
        try {
            result["stage"] = "library"
            if (mode == "missing-runtime") {
                check(!watch.runtimeAvailable && watch.errorKey == "playbackFailed" && watch.player == null)
                check("startWatching" !in watch.libraryPresentation(catalog.presentation).enabledActions)
                watch.close(); result["missingRuntimeRejected"] = true; result["success"] = true; result.remove("stage")
                finish(result, catalog, report, exit); return
            }
            check(watch.runtimeAvailable && watch.player == null && !watch.playerPresented)
            catalog.settled()
            if (catalog.presentation.entries.isEmpty()) { catalog.choose(file.parent); catalog.settled() }
            val entry = catalog.presentation.entries.single { it.title == file.fileName.toString() }
            catalog.select(entry.id)
            val selection = checkNotNull(catalog.selectedMedia())
            val expected = preferences.state.resumePositionFor(entry.id)
            result["restoredPositionMs"] = expected
            if (mode != "normal") {
                result["stage"] = mode; watch.start(selection)
                if (mode == "load-failure") {
                    until { watch.phase == WatchPhase.ended && watch.player == null }
                    check(watch.errorKey == "playbackFailed" && !watch.playerPresented); result["failedLoadReleased"] = true
                } else if (mode == "close-preparing") {
                    until { watch.player != null }; check(watch.phase == WatchPhase.preparing)
                    watch.close(); watch.close(); check(watch.player == null && !watch.playerPresented)
                    result["closeDuringPreparation"] = true
                } else if (mode == "cancel-correction") {
                    until { watch.player?.canvas?.isShowing == true && watch.phase == WatchPhase.active }
                    val current = checkNotNull(watch.player)
                    until { val v = current.player.observe(current.scope); v.status == PlaybackStatus.ready && v.seekable && v.paused }
                    current.player.seek(1300, current.scope); until { kotlin.math.abs(watch.positionMs - 1300) < 200 }
                    for (command in listOf("seek", "rate", "pause")) {
                        coroutineScope {
                            val operation = async {
                                currentCoroutineContext().cancel()
                                when (command) {
                                    "seek" -> current.player.seek(0, current.scope)
                                    "rate" -> current.player.setRate(1.25, current.scope)
                                    else -> current.player.setPaused(false, current.scope)
                                }
                            }
                            try { operation.await(); error("cancelled correction completed") }
                            catch (_: CancellationException) { }
                        }
                        delay(100)
                        val v = current.player.observe(current.scope)
                        check(v.paused && v.rate == 1.0 && kotlin.math.abs(v.positionMs - 1300) < 200)
                    }
                    result["cancelledCorrectionsPreserveNativeState"] = true
                } else error("watch check mode")
                watch.close(); result["success"] = true; result.remove("stage")
                finish(result, catalog, report, exit); return
            }
            result["stage"] = "start"
            watch.start(selection)
            until { watch.player?.canvas?.isShowing == true && watch.phase == WatchPhase.active }
            val player = checkNotNull(watch.player); val scope = player.scope; val canvas = player.canvas
            until { val v = player.player.observe(scope); v.status == PlaybackStatus.ready && v.paused && v.seekable && kotlin.math.abs(v.positionMs - expected) < 300 }
            until { player.presentation.allows("playPause") && !player.presentation.playing }
            watch.start(selection); check(watch.player === player && watch.scope == scope)
            fun action(name: String, number: Double? = null) = player.action(name, number, {}, {})
            action("playPause")
            until { val v = player.player.observe(scope); !v.paused && v.positionMs >= maxOf(500, expected + 200) }
            result["stage"] = "home-continue"
            action("showLibrary"); check(!watch.playerPresented && watch.player === player)
            val hidden = player.player.observe(scope).positionMs
            until { player.player.observe(scope).positionMs >= hidden + 250 }
            watch.continueWatching(); check(watch.playerPresented && watch.player === player && player.canvas === canvas && watch.scope == scope)
            until { player.presentation.playing }
            action("playPause"); until { player.player.observe(scope).paused }
            action("seek", 1300.0); until { kotlin.math.abs(watch.positionMs - 1300) < 200 }
            result["stage"] = "end-restart"
            watch.end(); until { watch.player == null && !preferences.savingWatchState }
            var released = false
            try { player.player.observe(scope) } catch (_: Exception) { released = true }
            check(released && watch.scope != scope && !watch.playerPresented)
            watch.start(selection)
            until { watch.player?.canvas?.isShowing == true && watch.phase == WatchPhase.active }
            val resumed = checkNotNull(watch.player)
            check(resumed !== player && resumed.scope != scope)
            until { val v = resumed.player.observe(resumed.scope); v.paused && kotlin.math.abs(v.positionMs - 1300) < 250 && kotlin.math.abs(watch.positionMs - 1300) < 250 }
            watch.end(); until { watch.player == null && !preferences.savingWatchState }
            result["stage"] = "cancel-close"
            watch.start(selection); watch.end(); watch.close(); watch.close()
            check(watch.player == null && !watch.playerPresented && kotlin.math.abs(preferences.state.resumePositionFor(entry.id) - 1300) < 250)
            for (name in listOf("sameOwnerHomeContinue", "nativeClockWhileHidden", "endReleasesNative", "resumeAfterNewOwner", "cancelBeforeAllocation", "idempotentClose")) result[name] = true
            result["success"] = true; result.remove("stage")
        } catch (error: Exception) {
            result["failure"] = error.toString()
            result["phase"] = watch.phase.name
            result["playerPresented"] = watch.playerPresented
            result["watchError"] = watch.errorKey.orEmpty()
            watch.player?.let {
                result["playerFailed"] = it.failed
                result["surfaceShowing"] = it.canvas.isShowing
                result["surfaceDisplayable"] = it.canvas.isDisplayable
                result["surfaceWidth"] = it.canvas.width
                result["surfaceHeight"] = it.canvas.height
                result["presentation"] = it.presentation.state.name
                try {
                    val v = it.player.observe(it.scope)
                    result["nativeStatus"] = v.status.name
                    result["nativePositionMs"] = v.positionMs
                    result["nativePaused"] = v.paused
                    result["nativeSeekable"] = v.seekable
                    result["nativeDurationMs"] = v.durationMs ?: -1
                } catch (observation: Exception) { result["observationFailure"] = observation.toString() }
            }
            watch.close()
        }
        finish(result, catalog, report, exit)
    }
    private fun finish(result: Map<String, Any>, catalog: LibraryController, report: Path, exit: () -> Unit) {
        catalog.close()
        Files.writeString(report, Json.write(result) + "\n", StandardOpenOption.CREATE_NEW)
        exit()
    }
}
