package syncwatch.playback

import java.nio.file.Path
import java.nio.file.Files
import java.security.MessageDigest
import java.util.concurrent.CompletableFuture
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.cancel
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import syncwatch.domain.PlaybackObservation
import syncwatch.domain.PlaybackScope
import syncwatch.domain.PlaybackStatus
import syncwatch.domain.WatchFailure
import syncwatch.domain.WatchSession

/** Kotlin checks run only on Linux; optional arguments enable real native engine checks. */
fun main(arguments: Array<String>) = runBlocking {
    val scope = PlaybackScope("kotlin-playback", 1)
    val value = PlaybackObservation(scope, 0uL, PlaybackStatus.ready, 100, 1000, true,
        1.0, true, false, false, 320, 180, 1, .5, false)
    val invalid = listOf<() -> PlaybackObservation>(
        { value.copy(positionMs = -1) }, { value.copy(positionMs = WatchSession.MAXIMUM_POSITION_MS + 1) },
        { value.copy(durationMs = 99) }, { value.copy(durationMs = -1) },
        { value.copy(rate = Double.NaN) }, { value.copy(rate = .24) }, { value.copy(rate = 4.01) },
        { value.copy(volume = Double.NaN) }, { value.copy(volume = -.1) }, { value.copy(volume = 1.1) },
        { value.copy(width = -1) }, { value.copy(height = -1) }, { value.copy(videoOutputs = -1) },
        { value.copy(status = PlaybackStatus.loading) },
        { value.copy(status = PlaybackStatus.unloaded, seekable = false) },
    )
    invalid.forEach { check(runCatching(it).exceptionOrNull() is WatchFailure) }
    value.copy(durationMs = null, volume = null)
    value.copy(status = PlaybackStatus.unloaded, positionMs = 0, durationMs = null, seekable = false)

    check(CompletableFuture.completedFuture(42).awaitNative() == 42)
    val pending = CompletableFuture<Int>()
    val waiting = launch(start = CoroutineStart.UNDISPATCHED) { pending.awaitNative() }
    waiting.cancelAndJoin()
    check(pending.isCancelled)
    val failure = IllegalStateException("expected-owner-rejection")
    check(runCatching { CompletableFuture.failedFuture<Int>(failure).awaitNative() }.exceptionOrNull() === failure)
    val empty = VLCPlayback()
    val closing = launch(start = CoroutineStart.UNDISPATCHED) {
        currentCoroutineContext().cancel()
        empty.close()
    }
    closing.join()
    check(empty.closeAsync().isDone)
    empty.close()
    check(runCatching { empty.load(Path.of("/unavailable"), scope) }.isFailure)

    if (arguments.isNotEmpty()) {
        require(arguments.size == 3)
        val player = VLCPlayback()
        suspend fun observed(condition: (PlaybackObservation) -> Boolean): PlaybackObservation = withTimeout(15_000) {
            var next = player.observe(scope)
            while (!condition(next)) {
                check(next.status != PlaybackStatus.failed && !next.ended)
                delay(20); next = player.observe(scope)
            }
            check(next.status != PlaybackStatus.failed && !next.ended)
            next
        }
        try {
            player.open(Path.of(arguments[0]), Path.of(arguments[1]))
            player.load(Path.of(arguments[2]), scope)
            check(observed { it.status == PlaybackStatus.ready && it.paused }.durationMs == 4000L)
            val content: syncwatch.domain.LoadedMediaContentPort = player
            val version = content.contentVersion(scope)
            check(version.sizeBytes == Files.size(Path.of(arguments[2])))
            check(version.toString() == "LoadedMediaVersion(redacted)")
            val digest = MessageDigest.getInstance("SHA-256")
            var offset = 0L
            while (offset < version.sizeBytes) {
                val chunk = content.readContent(offset, 262144, scope)
                check(chunk.isNotEmpty()); digest.update(chunk); offset += chunk.size
            }
            val expected = MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(Path.of(arguments[2])))
            check(digest.digest().contentEquals(expected))
            check(content.readContent(offset, 8, scope).isEmpty())
            check(content.contentVersion(scope) == version)
            check(runCatching { content.readContent(0, 262145, scope) }.isFailure)
            player.setPaused(false, scope)
            observed { !it.paused && it.positionMs >= 450 }
            player.setPaused(true, scope); observed { it.paused }
            player.seek(2500, scope); observed { it.paused && it.positionMs in 2300..2700 }
            player.seek(250, scope); observed { it.paused && it.positionMs <= 650 }
            check(player.tracks(false, scope).any { it.id >= 0 })
            val next = scope.replacingMedia()
            player.load(Path.of(arguments[2]), next)
            check(runCatching { content.contentVersion(scope) }.isFailure)
            check(runCatching { content.readContent(0, 8, scope) }.isFailure)
            check(content.contentVersion(next) != version)
            player.stop(next)
            check(runCatching { content.readContent(0, 8, next) }.isFailure)
            println("SYNCWATCH_KOTLIN_LOADED_CONTENT_OK")
        } finally { player.close() }
    }
    println("SYNCWATCH_KOTLIN_PLAYBACK_OK")
}
