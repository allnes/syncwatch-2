package syncwatch.library

import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.FileTime

enum class LibraryCompanionKind { audio, subtitles }

/** A local scan version; never a room descriptor or persisted native track ID. */
data class LocalCompanionFile(val id: String, val kind: LibraryCompanionKind, val relativePath: String,
    val file: Path, val sizeBytes: Long, val modificationTime: FileTime) {
    fun open(): LocalFileAccess {
        val access = LocalFileAccess.selected(file)
        val facts = Files.readAttributes(file, java.nio.file.attribute.BasicFileAttributes::class.java,
            java.nio.file.LinkOption.NOFOLLOW_LINKS)
        check(facts.isRegularFile && facts.size() == sizeBytes && facts.lastModifiedTime() == modificationTime) {
            "companion-changed"
        }
        return access
    }
}
