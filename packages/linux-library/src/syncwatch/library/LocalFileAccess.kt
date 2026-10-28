package syncwatch.library

import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.nio.file.Path

/** Transient explicit local-file selection; the native owner retains its actual read descriptor. */
class LocalFileAccess private constructor(val file: Path) {
    companion object {
        fun selected(file: Path): LocalFileAccess {
            require(file.isAbsolute && Files.isRegularFile(file, NOFOLLOW_LINKS)) { "local-file" }
            return LocalFileAccess(file.normalize())
        }
    }
}
