package syncwatch.library

import java.nio.file.*
import java.nio.file.attribute.BasicFileAttributes
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.withContext

enum class LibraryMonitorEvent { changed, unavailable }

/** Invalidations only. A bounded channel never substitutes event paths for a completed scan. */
class LibraryChangeMonitor private constructor(private val root: Path, private val recursive: Boolean,
    private val service: WatchService) : AutoCloseable {
    private val stopped = AtomicBoolean(false)
    private val failed = AtomicBoolean(false)
    private val events = Channel<LibraryMonitorEvent>(Channel.CONFLATED)
    val changes: ReceiveChannel<LibraryMonitorEvent> get() = events
    val isActive: Boolean get() = !stopped.get() && !failed.get()
    private val directories = HashMap<WatchKey, Path>()
    private lateinit var worker: Thread

    private fun register(directory: Path) {
        val key = directory.register(service, StandardWatchEventKinds.ENTRY_CREATE,
            StandardWatchEventKinds.ENTRY_DELETE, StandardWatchEventKinds.ENTRY_MODIFY)
        directories[key] = directory
    }
    private fun registerTree(directory: Path) {
        Files.walkFileTree(directory, object : SimpleFileVisitor<Path>() {
            override fun preVisitDirectory(path: Path, facts: BasicFileAttributes): FileVisitResult {
                register(path)
                return FileVisitResult.CONTINUE
            }
        })
    }
    private fun run() {
        try {
            while (!stopped.get()) {
                val key = service.take()
                val directory = directories[key] ?: continue
                for (event in key.pollEvents()) {
                    if (recursive && event.kind() == StandardWatchEventKinds.ENTRY_CREATE) {
                        val child = directory.resolve(event.context() as Path)
                        if (Files.isDirectory(child, LinkOption.NOFOLLOW_LINKS)) {
                            try { registerTree(child) } catch (_: NoSuchFileException) { /* Reconcile the deletion below. */ }
                        }
                    }
                    // OVERFLOW deliberately has the same reconciliation path.
                    events.trySend(LibraryMonitorEvent.changed)
                }
                if (!key.reset()) {
                    directories.remove(key)
                    if (directory == root) throw java.io.IOException("library-watch-root")
                }
            }
        } catch (_: ClosedWatchServiceException) {
            if (!stopped.get()) unavailable()
        } catch (_: Exception) {
            if (!stopped.get()) unavailable()
        } finally {
            service.close()
            events.close()
        }
    }
    private fun unavailable() { failed.set(true); events.trySend(LibraryMonitorEvent.unavailable) }
    override fun close() {
        if (stopped.compareAndSet(false, true)) service.close()
    }
    suspend fun closeAndWait() = withContext(Dispatchers.IO) { close(); worker.join() }

    companion object {
        /** Create off the UI thread; recursive registration does not follow symlink directories. */
        fun open(root: Path, recursive: Boolean): LibraryChangeMonitor {
            require(root.isAbsolute && Files.isDirectory(root)) { "library-watch-root" }
            val monitor = LibraryChangeMonitor(root.toRealPath(), recursive, root.fileSystem.newWatchService())
            try {
                if (recursive) monitor.registerTree(monitor.root) else monitor.register(monitor.root)
                monitor.worker = thread(name = "SyncWatch.LibraryChanges", isDaemon = true) { monitor.run() }
                return monitor
            } catch (error: Exception) { monitor.close(); throw error }
        }
    }
}
