package syncwatch.library

import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.BasicFileAttributes
import java.util.UUID

/** Local selected-folder owner. Restoring metadata rechecks current OS access. */
class LibraryFolderAccess private constructor(val record: LibraryAccessRecord) {
    val rootId: String get() = record.rootId
    val root: Path = Path.of(record.rootPath)
    init {
        record.validate()
        require(Files.readAttributes(root, BasicFileAttributes::class.java).isDirectory) { "library-root" }
    }
    companion object {
        fun selected(root: Path, scanSubfolders: Boolean = true, autoRefresh: Boolean = true): LibraryFolderAccess {
            require(root.isAbsolute) { "absolute-library-root" }
            return LibraryFolderAccess(LibraryAccessRecord(UUID.randomUUID().toString(), root.toAbsolutePath().normalize().toString(),
                scanSubfolders, autoRefresh))
        }
        fun restore(record: LibraryAccessRecord): LibraryFolderAccess = LibraryFolderAccess(record)
    }
}
