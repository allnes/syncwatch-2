package syncwatch.library

import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.FileTime
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.withContext
import syncwatch.ipc.Json

internal suspend fun fileContentHasherChecks(fixture: Path) {
    val root = Files.createTempDirectory("syncwatch-hash-")
    try {
        val corpus = Json.`object`(Json.parse(Files.readString(fixture.toAbsolutePath().parent.resolve("library-content.json"))))
        val file = root.resolve("owned 🎬.avi"); val scanner = FileSystemLibrary(); val hasher = FileContentHasher()
        val rootId = UUID.randomUUID().toString(); var last: LocalMediaFile? = null
        for (raw in corpus["cases"] as List<*>) {
            val p = Json.`object`(raw)
            Files.writeString(file, (p["content"] as String).repeat(Math.toIntExact(p["repeat"] as Long)))
            Files.setLastModifiedTime(file, FileTime.fromMillis(1_600_000_000_000))
            val media = scanner.scan(root, rootId, false).single()
            check(hasher.sha256(media) == p["sha256"]) { p["name"].toString() }; last = media
        }
        val selected = checkNotNull(last)
        Files.writeString(file, "longer")
        try { hasher.sha256(selected); error("Stale catalog accepted") } catch (failure: IllegalStateException) { check(failure.message == "media-changed") }
        Files.delete(file)
        try { hasher.sha256(selected); error("Missing file accepted") } catch (_: java.io.IOException) { }
        Files.writeString(file, "xyz"); val other = root.resolve("other"); Files.move(file, other)
        if (Files.getFileStore(root).supportsFileAttributeView("posix")) {
            Files.createSymbolicLink(file, other)
            try { hasher.sha256(selected); error("Symlink accepted") } catch (failure: IllegalStateException) { check(failure.message == "media-changed") }
        }
        try { withContext(Job().apply { cancel() }) { hasher.sha256(selected) }; error("Cancellation ignored") }
        catch (_: CancellationException) { }
        println("SYNCWATCH_FILE_CONTENT_OK streaming hash, invalidation, cancellation and release")
    } finally { Files.walk(root).use { paths -> paths.sorted(Comparator.reverseOrder()).forEach(Files::delete) } }
}
