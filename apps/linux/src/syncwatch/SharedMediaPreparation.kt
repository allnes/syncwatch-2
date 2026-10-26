package syncwatch

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.async
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import syncwatch.domain.*
import syncwatch.library.FileContentHasher

/** Owns cancellable preparation while retaining the selected folder grant. */
internal class SharedMediaPreparation(private val work: CoroutineScope) {
    private var pending: Deferred<MediaDescriptor>? = null
    private var closed = false
    suspend fun prepare(selection: LibraryMediaSelection, player: PlaybackPort, scope: PlaybackScope): MediaDescriptor {
        check(!closed)
        currentCoroutineContext().ensureActive()
        pending?.let { return await(it) }
        val task = work.async {
            try {
                val before = player.observe(scope)
                check(before.status == PlaybackStatus.ready && before.seekable && (before.durationMs ?: 0) > 0)
                val digest = FileContentHasher().sha256(selection.media)
                currentCoroutineContext().ensureActive()
                val after = player.observe(scope)
                check(after.status == PlaybackStatus.ready && after.seekable && after.durationMs == before.durationMs)
                val title = MediaDescriptor.logicalTitle(selection.media.title)
                MediaDescriptor(selection.media.id, title, MediaDescriptor.normalizedTitleKey(title),
                    selection.media.sizeBytes, before.durationMs, digest)
            } finally { java.lang.ref.Reference.reachabilityFence(selection.access) }
        }
        pending = task
        try { return await(task) } finally { if (pending === task) pending = null }
    }
    private suspend fun await(task: Deferred<MediaDescriptor>): MediaDescriptor {
        try { return task.await() }
        catch (cancelled: CancellationException) {
            task.cancel()
            withContext(NonCancellable) { task.join() }
            throw cancelled
        }
    }
    suspend fun close() { closed = true; pending?.cancelAndJoin() }
}
