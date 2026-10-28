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
    val file: Path, val sizeBytes: Long, val modificationTime: FileTime,
    val companions: List<LocalCompanionFile> = emptyList(), val folderMovie: Boolean = false)

/** The caller retains the selected folder grant. Failed/cancelled scans publish no snapshot. */
class FileSystemLibrary(private val companionExtensions: Map<String, LibraryCompanionKind> = emptyMap()) {
    suspend fun scan(root: Path, rootId: String, recursive: Boolean): List<LocalMediaFile> = withContext(Dispatchers.IO) {
        require(java.util.UUID.fromString(rootId).toString() == rootId) { "library-root-id" }
        require(root.isAbsolute) { "absolute-library-root" }
        val root = root.normalize()
        require(Files.readAttributes(root, BasicFileAttributes::class.java).isDirectory) { "library-root" }
        val pending = ArrayDeque<Pair<Path, String>>()
        pending.add(root to "")
        val files = ArrayList<LocalMediaFile>()
        val companions = ArrayList<LocalCompanionFile>()
        val caseSensitive = HashMap<String, Boolean>()
        while (pending.isNotEmpty()) {
            currentCoroutineContext().ensureActive()
            val (directory, relativeDirectory) = pending.removeLast()
            Files.newDirectoryStream(directory).use { listing ->
                val children = listing.toList()
                val names = children.map { it.fileName.toString() }.toSet()
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
                    if (!facts.isRegularFile || dot < 0) continue
                    val extensionName = filename.substring(dot + 1)
                    val video = extensionName.lowercase() in extensions
                    val kind = companionExtensions[extensionName.lowercase()]
                    if (!video && kind == null) continue
                    val id = MessageDigest.getInstance("SHA-256").digest((rootId + "\u0000" + relative).toByteArray(UTF_8))
                        .joinToString("") { "%02x".format(it.toInt() and 255) }
                    if (!video && kind != null) {
                        companions.add(LocalCompanionFile(id, kind, relative, child, facts.size(), facts.lastModifiedTime()))
                        continue
                    }
                    caseSensitive.getOrPut(relativeDirectory) {
                        // Read-only probe of a known ASCII extension in this directory.
                        val alternate = filename.substring(0, dot + 1) + extensionName.map {
                            if (it.isUpperCase()) it.lowercaseChar() else it.uppercaseChar()
                        }.joinToString("")
                        alternate in names || !Files.exists(directory.resolve(alternate), NOFOLLOW_LINKS)
                    }
                    files.add(LocalMediaFile(id, filename, relative, child, facts.size(), facts.lastModifiedTime()))
                }
            }
        }
        currentCoroutineContext().ensureActive()
        val paths = files.map { it.relativePath }
        val audio = companions.filter { it.kind == LibraryCompanionKind.audio }.map { it.relativePath }
        val subtitles = companions.filter { it.kind == LibraryCompanionKind.subtitles }.map { it.relativePath }
        val sensitive = LibraryFileIndex(paths, audio, subtitles, true)
        val insensitive = LibraryFileIndex(paths, audio, subtitles, false)
        val byPath = companions.associateBy { it.relativePath }
        for (position in files.indices) {
            currentCoroutineContext().ensureActive()
            val file = files[position]
            val directory = file.relativePath.substringBeforeLast('/', "").let { if (it.isEmpty()) "" else "$it/" }
            val index = if (caseSensitive[directory] == false) insensitive else sensitive
            val extras = (index.audioPaths(file.relativePath) + index.subtitlePaths(file.relativePath)).mapNotNull { byPath[it] }
            files[position] = file.copy(companions = java.util.Collections.unmodifiableList(extras), folderMovie = index.isFolderMovie(file.relativePath))
        }
        files.sortWith { a, b -> java.util.Arrays.compareUnsigned(a.relativePath.toByteArray(UTF_8), b.relativePath.toByteArray(UTF_8)) }
        java.util.Collections.unmodifiableList(files)
    }
    private companion object {
        val extensions = setOf("mkv", "mp4", "avi", "mov", "m4v", "webm", "wmv", "mpg", "mpeg", "ts", "m2ts")
    }
}
