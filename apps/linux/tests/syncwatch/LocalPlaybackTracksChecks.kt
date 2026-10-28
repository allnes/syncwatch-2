package syncwatch

import java.nio.file.Path
import kotlin.coroutines.Continuation
import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import syncwatch.design.*
import syncwatch.domain.*

private class TrackPlayer : PlaybackTrackControlPort {
    var selected = 1
    var reject = false
    var hold = false
    var waiting: Continuation<Unit>? = null
    var selections = 0
    var reads = 0
    var lastScope: PlaybackScope? = null
    fun release() { val next = waiting; waiting = null; next?.resume(Unit) }
    override suspend fun tracks(subtitles: Boolean, scope: PlaybackScope): List<PlaybackTrack> {
        reads++; lastScope = scope
        if (hold) suspendCoroutine<Unit> { waiting = it } // Deliberately ignore cancellation.
        return listOf(PlaybackTrack(-1, "Disable"), PlaybackTrack(1, "First"), PlaybackTrack(2, "Second"))
    }
    override suspend fun selectedTrack(subtitles: Boolean, scope: PlaybackScope) = selected
    override suspend fun selectTrack(id: Int, subtitles: Boolean, scope: PlaybackScope) { selections++; check(!reject) }
    override suspend fun load(localFile: Path, scope: PlaybackScope) = error("unused")
    override suspend fun observe(scope: PlaybackScope): PlaybackObservation = error("unused")
    override suspend fun setPaused(paused: Boolean, scope: PlaybackScope) = error("unused")
    override suspend fun seek(positionMs: Long, scope: PlaybackScope) = error("unused")
    override suspend fun setRate(rate: Double, scope: PlaybackScope) = error("unused")
    override suspend fun setVolume(volume: Double, muted: Boolean, scope: PlaybackScope) = error("unused")
    override suspend fun stop(scope: PlaybackScope) = error("unused")
    override suspend fun close() = Unit
}

internal suspend fun localPlaybackTracksChecks(owner: CoroutineScope) {
    val player = TrackPlayer(); val scope = PlaybackScope.fresh().replacingMedia()
    val model = LocalPlaybackTracks(player, scope, owner)
    suspend fun until(condition: () -> Boolean) = withTimeout(2_000) { while (!condition()) delay(5) }
    try {
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
    println("SYNCWATCH_LOCAL_TRACKS_OK acknowledgement, stale input, late completion, retry, awaited close")
}
