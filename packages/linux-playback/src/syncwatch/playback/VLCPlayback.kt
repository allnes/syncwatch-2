package syncwatch.playback

import java.nio.file.Path
import java.util.concurrent.CompletableFuture
import java.util.concurrent.CompletionException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import syncwatch.domain.PlaybackObservation
import syncwatch.domain.PlaybackTrackControlPort
import syncwatch.domain.PlaybackScope
import syncwatch.domain.PlaybackStatus
import syncwatch.domain.PlaybackTrack
import syncwatch.domain.LoadedMediaContentPort
import syncwatch.domain.LoadedMediaVersion

/** Domain adapter only. JNI worker, native surface lifetime and common design have independent owners. */
class VLCPlayback : PlaybackTrackControlPort, LoadedMediaContentPort {
    private val native = NativePlayback()

    companion object {
        /** Must run before constructing the application toolkit. */
        fun initializeDisplay(bridge: Path, packageDirectory: Path): X11Display {
            val runtime = MediaRuntime.verify(packageDirectory)
            return X11Display.initializeVerified(bridge, runtime.library().parent.resolve("libX11.so.6"))
        }
    }

    suspend fun open(bridge: Path, packageDirectory: Path, canvas: X11VideoCanvas) {
        open(bridge, packageDirectory, canvas.surface().awaitNative())
    }

    suspend fun open(bridge: Path, packageDirectory: Path, surface: X11Display.Surface? = null) {
        val runtime = withContext(Dispatchers.IO) { MediaRuntime.verify(packageDirectory) }
        if (surface == null) native.openVerified(bridge, runtime.library(), runtime.revision()).awaitNative()
        else native.openX11Verified(bridge, runtime.library(), runtime.revision(), surface).awaitNative()
    }

    private suspend fun PlaybackScope.nativeScope(): NativePlayback.Scope {
        // Resolve before submitting a future; cancellation during await alone
        // can arrive after the native worker has already started the command.
        currentCoroutineContext().ensureActive()
        return NativePlayback.Scope(clientRunId, mediaGeneration)
    }
    override suspend fun load(localFile: Path, scope: PlaybackScope) { native.load(localFile, scope.nativeScope()).awaitNative() }
    override suspend fun contentVersion(scope: PlaybackScope): LoadedMediaVersion {
        val value = native.contentVersion(scope.nativeScope()).awaitNative()
        val stamp = value.joinToString("") { java.lang.Long.toUnsignedString(it, 16).padStart(16, '0') }
        return LoadedMediaVersion(scope, value[3], stamp)
    }
    override suspend fun readContent(offset: Long, capacity: Int, scope: PlaybackScope): ByteArray =
        native.readContent(offset, capacity, scope.nativeScope()).awaitNative()
    override suspend fun observe(scope: PlaybackScope): PlaybackObservation {
        val value = native.observe(scope.nativeScope()).awaitNative()
        val owner = PlaybackScope(value.scope().clientRunId(), value.scope().generation())
        scope.check(owner)
        return PlaybackObservation(owner, value.sequence().toULong(), PlaybackStatus.entries[value.status()],
            value.positionMs(), value.durationMs(), value.paused(), value.rate(), value.seekable(),
            value.buffering(), value.ended(), value.width(), value.height(), value.videoOutputs(), value.volume(), value.muted())
    }
    override suspend fun setPaused(paused: Boolean, scope: PlaybackScope) {
        native.pause(paused, scope.nativeScope()).awaitNative()
    }
    override suspend fun seek(positionMs: Long, scope: PlaybackScope) {
        native.seek(positionMs, scope.nativeScope()).awaitNative()
    }
    override suspend fun setRate(rate: Double, scope: PlaybackScope) {
        native.rate(rate, scope.nativeScope()).awaitNative()
    }
    override suspend fun setVolume(volume: Double, muted: Boolean, scope: PlaybackScope) {
        native.volume(volume, muted, scope.nativeScope()).awaitNative()
    }
    override suspend fun tracks(subtitles: Boolean, scope: PlaybackScope): List<PlaybackTrack> =
        native.tracks(subtitles, scope.nativeScope()).awaitNative().map { PlaybackTrack(it.id(), it.name()) }
    override suspend fun selectTrack(id: Int, subtitles: Boolean, scope: PlaybackScope) {
        native.selectTrack(id, subtitles, scope.nativeScope()).awaitNative()
    }
    override suspend fun selectedTrack(subtitles: Boolean, scope: PlaybackScope): Int =
        native.selectedTrack(subtitles, scope.nativeScope()).awaitNative()
    override suspend fun stop(scope: PlaybackScope) { native.stop(scope.nativeScope()).awaitNative() }
    fun closeAsync(): CompletableFuture<Void> = native.closeAsync()
    override suspend fun close() { withContext(NonCancellable) { closeAsync().awaitNative() } }
}

/** Cancellation rejects queued work; it never interrupts a native call already executing. */
internal suspend fun <T> CompletableFuture<T>.awaitNative(): T = suspendCancellableCoroutine { continuation ->
    whenComplete { value, error ->
        if (error == null) continuation.resume(value)
        else continuation.resumeWithException(if (error is CompletionException) error.cause ?: error else error)
    }
    continuation.invokeOnCancellation { cancel(false) }
}
