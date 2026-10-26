package syncwatch.library

import java.nio.ByteBuffer
import java.nio.channels.FileChannel
import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.nio.file.Path
import java.nio.file.StandardOpenOption.READ
import java.nio.file.attribute.BasicFileAttributes
import java.nio.file.attribute.FileTime
import java.security.MessageDigest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/** Serialized bounded background hashing. The caller retains the folder grant. */
class FileContentHasher {
    private data class Snapshot(val key: Any?, val size: Long, val modified: FileTime, val created: FileTime)
    private val pending = Mutex()
    /** The caller owns and validates the source version; no path is reopened. */
    suspend fun sha256(sizeBytes: Long, readChunk: suspend (Long, Int) -> ByteArray): String =
        withContext(Dispatchers.IO) { pending.withLock {
            require(sizeBytes >= 0)
            val hash = MessageDigest.getInstance("SHA-256")
            var offset = 0L
            while (offset < sizeBytes) {
                currentCoroutineContext().ensureActive()
                val capacity = minOf(262144L, sizeBytes - offset).toInt()
                val chunk = readChunk(offset, capacity)
                check(chunk.isNotEmpty() && chunk.size <= capacity) { "media-changed" }
                hash.update(chunk); offset += chunk.size
            }
            currentCoroutineContext().ensureActive()
            check(readChunk(sizeBytes, 1).isEmpty()) { "media-changed" }
            currentCoroutineContext().ensureActive()
            hash.digest().joinToString("") { "%02x".format(it.toInt() and 255) }
        } }
    private fun snapshot(path: Path): Snapshot {
        val facts = Files.readAttributes(path, BasicFileAttributes::class.java, NOFOLLOW_LINKS)
        check(facts.isRegularFile && !facts.isSymbolicLink) { "media-changed" }
        return Snapshot(facts.fileKey(), facts.size(), facts.lastModifiedTime(), facts.creationTime())
    }
    suspend fun sha256(media: LocalMediaFile): String = withContext(Dispatchers.IO) { pending.withLock {
        currentCoroutineContext().ensureActive()
        val before = snapshot(media.file)
        check(before.size == media.sizeBytes && before.modified == media.modificationTime) { "media-changed" }
        FileChannel.open(media.file, READ, NOFOLLOW_LINKS).use { file ->
            check(file.size() == before.size && snapshot(media.file) == before) { "media-changed" }
            val hash = MessageDigest.getInstance("SHA-256"); val buffer = ByteBuffer.allocate(262_144)
            var total = 0L
            while (true) {
                currentCoroutineContext().ensureActive()
                val count = file.read(buffer)
                if (count < 0) break
                total += count; check(total <= before.size) { "media-changed" }
                buffer.flip(); hash.update(buffer); buffer.clear()
            }
            currentCoroutineContext().ensureActive()
            check(total == before.size && file.size() == before.size && snapshot(media.file) == before) { "media-changed" }
            val digest = hash.digest().joinToString("") { "%02x".format(it.toInt() and 255) }
            digest
        }
    } }
}
