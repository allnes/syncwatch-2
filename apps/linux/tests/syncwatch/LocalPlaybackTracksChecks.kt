package syncwatch

import java.nio.file.Path
import java.nio.file.Files
import syncwatch.library.LocalFileAccess
import kotlin.coroutines.Continuation
import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine
import kotlinx.coroutines.async
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import syncwatch.design.*
import syncwatch.domain.*

private class TrackPlayer : PlaybackExternalTrackPort {
    var selected = 1
    var autoAcknowledge = false
    var reject = false
    var hold = false
    var waiting: Continuation<Unit>? = null
    var selections = 0
    var reads = 0
    var lastScope: PlaybackScope? = null
    var attachments = 0
    private var attached = false
    fun release() { val next = waiting; waiting = null; next?.resume(Unit) }
    override suspend fun tracks(subtitles: Boolean, scope: PlaybackScope): List<PlaybackTrack> {
        reads++; lastScope = scope
        if (hold) suspendCoroutine<Unit> { waiting = it } // Deliberately ignore cancellation.
        val entries = listOf(PlaybackTrack(-1, "Disable"), PlaybackTrack(1, "First"), PlaybackTrack(2, "Second"))
        return if (attached) entries + PlaybackTrack(3, "External") else entries
    }
    override suspend fun selectedTrack(subtitles: Boolean, scope: PlaybackScope) = selected
    override suspend fun selectTrack(id: Int, subtitles: Boolean, scope: PlaybackScope) { selections++; check(!reject); if (autoAcknowledge) selected = id }
    override suspend fun load(localFile: Path, scope: PlaybackScope) = error("unused")
    override suspend fun observe(scope: PlaybackScope): PlaybackObservation = error("unused")
    override suspend fun setPaused(paused: Boolean, scope: PlaybackScope) = error("unused")
    override suspend fun seek(positionMs: Long, scope: PlaybackScope) = error("unused")
    override suspend fun setRate(rate: Double, scope: PlaybackScope) = error("unused")
    override suspend fun setVolume(volume: Double, muted: Boolean, scope: PlaybackScope) = error("unused")
    override suspend fun stop(scope: PlaybackScope) = error("unused")
    override suspend fun close() = Unit
    override suspend fun attachTrack(localFile: Path, subtitles: Boolean, scope: PlaybackScope) {
        attachments++; lastScope = scope; check(!reject)
        attached = true; if (autoAcknowledge) selected = 3
    }
}

private class TrackFilePicker : ExternalTrackChoosing {
    var file: LocalFileAccess? = null
    var hold = false
    var calls = 0
    var waiting: Continuation<LocalFileAccess?>? = null
    override suspend fun choose(kind: String, language: String): LocalFileAccess? {
        calls++
        return if (hold) suspendCoroutine { waiting = it } else file
    }
    override fun cancel() = Unit // Deliberately late to exercise the coordinator's join/identity guard.
    fun release() { val next = waiting; waiting = null; next?.resume(file) }
}

private suspend fun externalTrackFileChecks(owner: CoroutineScope) {
    val directory = Files.createTempDirectory("syncwatch-external-")
    val file = directory.resolve("Audio Кино 映画.wav")
    Files.writeString(file, "owned choice fixture")
    val player = TrackPlayer(); val picker = TrackFilePicker()
    val model = LocalPlaybackTracks(player, PlaybackScope.fresh().replacingMedia(), owner, picker)
    suspend fun until(condition: () -> Boolean) = withTimeout(2_000) { while (!condition()) delay(5) }
    fun choose(): SelectionMenuRequest {
        val menu = checkNotNull(model.menu); var request: SelectionMenuRequest? = null
        menu.dispatch(SyncWatchSelectionMenu.externalFileID, menu.contextToken) { request = it }
        return checkNotNull(request)
    }
    try {
        model.open("audio", "ru"); model.settled()
        check(model.menu?.entries?.last()?.label == SyncWatchCopy.text("openAudioTrack", "ru"))
        model.select(choose()); model.settled(); check(player.attachments == 0 && player.selected == 1)
        picker.file = LocalFileAccess.selected(file)
        val old = choose(); model.select(old); until { player.attachments == 1 }
        check(model.menu == null); model.dismissMenu(); check(player.selected == 1)
        player.selected = 3; model.settled()
        model.open("audio"); model.settled()
        check(model.menu?.selectedID == "3" && model.menu?.entries?.first { it.id == "3" }?.label == file.fileName.toString())
        model.select(old); check(player.attachments == 1)
        player.reject = true; model.select(choose()); model.settled()
        check(model.menu?.isValid == true && model.menu?.entries?.any { it.id == SyncWatchSelectionMenu.externalFileErrorID && !it.enabled } == true)
        player.reject = false; picker.hold = true; model.select(choose()); until { picker.waiting != null }
        model.dismissMenu(); check(model.menu == null && picker.waiting != null)
        val before = player.attachments
        val closing = owner.async { model.close() }
        until { model.menu == null }; check(!closing.isCompleted)
        picker.release(); closing.await()
        check(player.attachments == before && model.menu == null)
        model.releaseExternalAccess()
    } finally {
        picker.release(); model.close(); model.releaseExternalAccess()
        Files.deleteIfExists(file); Files.deleteIfExists(directory)
    }
}

internal suspend fun localPlaybackTracksChecks(owner: CoroutineScope) {
    val player = TrackPlayer(); val scope = PlaybackScope.fresh().replacingMedia()
    val model = LocalPlaybackTracks(player, scope, owner)
    suspend fun until(condition: () -> Boolean) = withTimeout(2_000) { while (!condition()) delay(5) }
    try {
        val invalid = LocalTrackPreferences(listOf("First", "Second"), listOf("Changed"), 1)
        check(runCatching { model.applyInitial(invalid) }.isFailure && player.selections == 0)
        val initialPreferences = LocalTrackPreferences(listOf("First", "Second"), listOf("First", "Second"), 1)
        val applying = owner.async { model.applyInitial(initialPreferences) }
        until { player.selections == 1 }; check(model.menu == null)
        player.autoAcknowledge = true; player.selected = 2; applying.await()
        check(player.selections == 2 && player.selected == -1)
        player.autoAcknowledge = false; player.selected = 1; player.selections = 0
        model.open("audio"); model.settled(); check(player.lastScope == scope)
        val initial = checkNotNull(model.menu); var request: SelectionMenuRequest? = null
        initial.dispatch("2", initial.contextToken) { request = it }
        model.select(checkNotNull(request)); until { player.selections == 1 }
        check(model.menu?.enabled == false && model.menu?.selectedID == "1")
        player.selected = 2; model.settled(); check(model.menu == null)
        model.open("audio"); model.settled(); check(model.menu?.enabled == true && model.menu?.selectedID == "2")
        model.select(checkNotNull(request)); check(player.selections == 1)
        player.reject = true
        val current = checkNotNull(model.menu); current.dispatch("1", current.contextToken, model::select)
        model.settled(); check(model.menu?.isValid == false)
        player.reject = false; model.open("subtitles"); model.settled()
        check(model.menu?.isValid == true && model.menu?.kind == "subtitles")
        player.hold = true; val before = player.reads
        model.open("audio"); until { player.reads == before + 1 }
        model.open("subtitles"); model.dismiss(); player.release(); model.settled(); check(model.menu == null)
        model.open("audio"); until { player.reads == before + 2 }
        val closing = owner.launch { model.close() }; delay(5); check(!closing.isCompleted)
        player.release(); closing.join(); check(model.menu == null)
        model.open("audio"); check(model.menu == null)
    } finally { player.release(); model.close() }
    externalTrackFileChecks(owner)
    println("SYNCWATCH_LOCAL_TRACKS_OK acknowledgement, stale input, late completion, retry, awaited close")
}
