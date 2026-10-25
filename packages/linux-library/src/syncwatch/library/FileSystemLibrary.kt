package syncwatch.library

import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.nio.file.Path
import java.nio.file.attribute.BasicFileAttributes
import java.nio.file.attribute.FileTime
import java.security.MessageDigest
import java.util.ArrayDeque
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext

/** Local filesystem facts. Paths and timestamps never form a peer media descriptor. */
data class LocalMediaFile(val id: String, val title: String, val relativePath: String,
    val file: Path, val sizeBytes: Long, val modificationTime: FileTime)

/** The caller retains the selected folder grant. Failed/cancelled scans publish no snapshot. */
class FileSystemLibrary {
    suspend fun scan(root: Path, rootId: String, recursive: Boolean): List<LocalMediaFile> = withContext(Dispatchers.IO) {
        require(java.util.UUID.fromString(rootId).toString() == rootId) { "library-root-id" }
        require(root.isAbsolute) { "absolute-library-root" }
        val root = root.normalize()
        require(Files.readAttributes(root, BasicFileAttributes::class.java).isDirectory) { "library-root" }
        val pending = ArrayDeque<Pair<Path, String>>()
        pending.add(root to "")
        val files = ArrayList<LocalMediaFile>()
        while (pending.isNotEmpty()) {
            currentCoroutineContext().ensureActive()
            val (directory, relativeDirectory) = pending.removeLast()
            Files.newDirectoryStream(directory).use { children ->
                for (child in children) {
                    currentCoroutineContext().ensureActive()
                    val facts = Files.readAttributes(child, BasicFileAttributes::class.java, NOFOLLOW_LINKS)
                    if (facts.isSymbolicLink) continue
                    val relative = relativeDirectory + child.fileName.toString()
                    if (facts.isDirectory) {
                        if (recursive) pending.add(child to "$relative/")
                        continue
                    }
                    val filename = child.fileName.toString()
                    val dot = filename.lastIndexOf('.')
                    if (!facts.isRegularFile || dot < 0 || filename.substring(dot + 1).lowercase() !in extensions) continue
                    val id = MessageDigest.getInstance("SHA-256").digest((rootId + "\u0000" + relative).toByteArray(UTF_8))
                        .joinToString("") { "%02x".format(it.toInt() and 255) }
                    files.add(LocalMediaFile(id, filename, relative, child, facts.size(), facts.lastModifiedTime()))
                }
            }
        }
        currentCoroutineContext().ensureActive()
        files.sortWith { a, b -> java.util.Arrays.compareUnsigned(a.relativePath.toByteArray(UTF_8), b.relativePath.toByteArray(UTF_8)) }
        java.util.Collections.unmodifiableList(files)
    }
    private companion object {
        val extensions = setOf("mkv", "mp4", "avi", "mov", "m4v", "webm", "wmv", "mpg", "mpeg", "ts", "m2ts")
    }
}
