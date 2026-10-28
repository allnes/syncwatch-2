package syncwatch.library

import java.nio.file.Files
import java.nio.file.Path
import kotlinx.coroutines.withTimeout
import syncwatch.ipc.Json

suspend fun libraryChangeMonitorChecks(fixture: Path) {
    @Suppress("UNCHECKED_CAST")
    val corpus = Json.parse(Files.readString(fixture.resolveSibling("library-monitor.json"))) as Map<String, String>
    for (recursive in listOf(false, true)) {
        val root = Files.createTempDirectory("syncwatch-library-monitor-")
        val monitor = LibraryChangeMonitor.open(root, recursive)
        val scanner = FileSystemLibrary()
        suspend fun reconcile(paths: List<String>, size: Long? = null) = withTimeout(8000) {
            while (true) {
                check(monitor.changes.receive() == LibraryMonitorEvent.changed)
                val files = scanner.scan(root, corpus.getValue("rootId"), recursive)
                if (files.map { it.relativePath } == paths && (size == null || files.firstOrNull()?.sizeBytes == size)) break
            }
        }
        try {
            Files.writeString(root.resolve(corpus.getValue("created")), corpus.getValue("content"))
            reconcile(listOf(corpus.getValue("created")))
            Files.move(root.resolve(corpus.getValue("created")), root.resolve(corpus.getValue("renamed")))
            reconcile(listOf(corpus.getValue("renamed")))
            Files.writeString(root.resolve(corpus.getValue("renamed")), corpus.getValue("replacement"))
            reconcile(listOf(corpus.getValue("renamed")), corpus.getValue("replacement").toByteArray().size.toLong())
            val nested = root.resolve(corpus.getValue("nested"))
            Files.createDirectories(nested.parent); Files.writeString(nested, corpus.getValue("content"))
            reconcile((if (recursive) listOf(corpus.getValue("nested"), corpus.getValue("renamed")) else listOf(corpus.getValue("renamed"))).sorted())
            Files.delete(root.resolve(corpus.getValue("renamed")))
            reconcile(if (recursive) listOf(corpus.getValue("nested")) else emptyList())
            monitor.closeAndWait()
            while (monitor.changes.tryReceive().isSuccess) { }
            check(!monitor.isActive && monitor.changes.receiveCatching().isClosed)
            Files.writeString(root.resolve(corpus.getValue("created")), corpus.getValue("content"))
            check(monitor.changes.receiveCatching().isClosed)
        } finally {
            monitor.closeAndWait()
            root.toFile().deleteRecursively(); check(!Files.exists(root))
        }
    }
}
