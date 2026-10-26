package syncwatch

import java.nio.file.Path
import kotlinx.coroutines.*
import syncwatch.domain.*

private class WaitingMediaPlayer : PlaybackPort {
    val entered = CompletableDeferred<Unit>(); val stopped = CompletableDeferred<Unit>()
    override suspend fun observe(scope: PlaybackScope): PlaybackObservation {
        entered.complete(Unit)
        try { delay(30_000); error("unexpected observation") } finally { stopped.complete(Unit) }
    }
    override suspend fun load(localFile: Path, scope: PlaybackScope) { error("unexpected load") }
    override suspend fun setPaused(paused: Boolean, scope: PlaybackScope) { error("unexpected pause") }
    override suspend fun seek(positionMs: Long, scope: PlaybackScope) { error("unexpected seek") }
    override suspend fun setRate(rate: Double, scope: PlaybackScope) { error("unexpected rate") }
    override suspend fun setVolume(volume: Double, muted: Boolean, scope: PlaybackScope) { error("unexpected volume") }
    override suspend fun tracks(subtitles: Boolean, scope: PlaybackScope): List<PlaybackTrack> = error("unexpected tracks")
    override suspend fun selectTrack(id: Int, subtitles: Boolean, scope: PlaybackScope) { error("unexpected track") }
    override suspend fun stop(scope: PlaybackScope) { error("unexpected stop") }
    override suspend fun close() {}
}

internal suspend fun sharedMediaPreparationChecks(selection: LibraryMediaSelection, owner: CoroutineScope) {
    for (closeOwner in listOf(false, true)) {
        val preparation = SharedMediaPreparation(owner); val player = WaitingMediaPlayer()
        val worker = owner.async { preparation.prepare(selection, player, PlaybackScope.fresh()) }
        try {
            withTimeout(2_000) { player.entered.await() }
            if (closeOwner) withTimeout(2_000) { preparation.close() } else worker.cancel()
            val stoppedBeforeCleanup = withTimeoutOrNull(1_000) { player.stopped.await(); true } ?: false
            preparation.close(); preparation.close()
            check(stoppedBeforeCleanup) { "preparation outlived cancellation" }
            try { worker.await(); error("Canceled preparation succeeded") } catch (_: CancellationException) { }
        } finally { preparation.close(); worker.cancelAndJoin() }
    }
    println("SYNCWATCH_SHARED_MEDIA_PREPARATION_OK caller cancellation and repeated owner close")
}
