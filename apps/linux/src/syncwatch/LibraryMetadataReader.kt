package syncwatch

import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.nio.file.attribute.BasicFileAttributes
import java.util.UUID
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import syncwatch.domain.PlaybackScope
import syncwatch.domain.PlaybackStatus
import syncwatch.library.LocalMediaFile
import syncwatch.library.MediaMetadata
import syncwatch.library.MediaMetadataReader as MetadataPort
import syncwatch.playback.VLCPlayback

/** One serialized, silent paused VLC owner, independent of watch and room state. */
internal class LibraryMetadataReader(private val media: MediaConfiguration) : MetadataPort {
    private val player = VLCPlayback()
    private val serial = Mutex()
    private val runId = "metadata-${UUID.randomUUID()}"
    private var generation = 0L
    private var opened = false
    private var closed = false
    override suspend fun read(file: LocalMediaFile): MediaMetadata = serial.withLock {
        check(!closed) { "metadata-closed" }
        var scope: PlaybackScope? = null
        try {
            if (!opened) { player.open(media.bridge, media.packageDirectory); opened = true }
            currentCoroutineContext().ensureActive()
            val owner = PlaybackScope(runId, ++generation); scope = owner
            player.load(file.file, owner)
            val version = player.contentVersion(owner)
            check(version.sizeBytes == file.sizeBytes) { "metadata-input-changed" }
            val started = System.nanoTime()
            var result: MediaMetadata? = null
            while (System.nanoTime() - started < 3_000_000_000L) {
                currentCoroutineContext().ensureActive()
                val value = player.observe(owner)
                check(value.status != PlaybackStatus.failed) { "metadata-unavailable" }
                if (value.status == PlaybackStatus.ready && !value.buffering) {
                    val audio = player.tracks(false, owner).count { it.id >= 0 }
                    val subtitles = player.tracks(true, owner).count { it.id >= 0 }
                    result = MediaMetadata(value.durationMs, value.width, value.height, audio, subtitles)
                    if (value.durationMs != null && value.width > 0 && value.height > 0) break
                }
                delay(50)
            }
            check(result != null) { "metadata-unavailable" }
            check(player.contentVersion(owner) == version) { "metadata-input-changed" }
            val facts = withContext(Dispatchers.IO) { Files.readAttributes(file.file, BasicFileAttributes::class.java, NOFOLLOW_LINKS) }
            check(facts.isRegularFile && facts.size() == file.sizeBytes && facts.lastModifiedTime() == file.modificationTime) { "metadata-input-changed" }
            requireNotNull(result)
        } finally {
            withContext(NonCancellable) { scope?.let { runCatching { player.stop(it) } } }
        }
    }
    override suspend fun close() = withContext(NonCancellable) { serial.withLock { closed = true; player.close() } }
}
