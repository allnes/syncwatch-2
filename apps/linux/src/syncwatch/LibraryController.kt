package syncwatch

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import java.nio.file.Path
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import syncwatch.design.LibraryEntry
import syncwatch.design.LibraryPresentation
import syncwatch.design.LibraryVisualState
import syncwatch.library.*

/** Local selection ownership only; the path-based catalog ID is not peer content identity. */
internal data class LibraryMediaSelection(val media: LocalMediaFile, val access: LibraryFolderAccess)

/** UI coordination only. The library services and shared design own their respective boundaries. */
internal class LibraryController(private val store: LibraryAccessStore, parent: CoroutineScope, private val savedSelection: String?) {
    private val scope = CoroutineScope(parent.coroutineContext + SupervisorJob(parent.coroutineContext[Job]))
    private val persistence = Mutex()
    private val scanner = FileSystemLibrary()
    private var pending: Job? = null
    private var grant: LibraryFolderAccess? = null
    private var catalog = emptyMap<String, LocalMediaFile>()
    private var stable: LibraryPresentation? = null
    private var generation = 0L
    private var closed = false
    var presentation by mutableStateOf(LibraryPresentation(enabledActions = setOf("chooseFolder", "openSettings")))
        private set
    var errorKey by mutableStateOf<String?>(null)
        private set
    fun restore() = start {
        val value = storage { store.read() }
        when (value.status) {
                LibraryAccessStatus.loaded -> withContext(Dispatchers.IO) { LibraryFolderAccess.restore(requireNotNull(value.record)) }
                LibraryAccessStatus.missing, LibraryAccessStatus.invalid -> null
                LibraryAccessStatus.unsupportedVersion -> error("unsupported-library-version")
        }
    }
    fun choose(path: Path) = start { withContext(Dispatchers.IO) { LibraryFolderAccess.selected(path) } }
    fun rescan() { grant?.let { current -> start { current } } }
    fun select(id: String) {
        if (!closed) presentation.dispatch("selectMovie", id) { _, _ -> presentation = presentation.copy(selectedID = id); stable = presentation }
    }
    fun selectedMedia(): LibraryMediaSelection? {
        check(java.awt.EventQueue.isDispatchThread()) { "library-event-thread" }
        if (closed || presentation.state != LibraryVisualState.selected) return null
        val media = catalog[presentation.selectedID] ?: return null
        return LibraryMediaSelection(media, grant ?: return null)
    }
    fun clearError() { errorKey = null }
    fun close() {
        closed = true; generation++; pending?.cancel(); scope.cancel(); grant = null; catalog = emptyMap()
        presentation = presentation.copy(enabledActions = emptySet())
    }
    suspend fun settled() { pending?.join() }
    private suspend fun <T> storage(operation: () -> T): T = persistence.withLock { withContext(Dispatchers.IO) { operation() } }
    private fun start(acquire: suspend () -> LibraryFolderAccess?) {
        if (closed) return
        pending?.cancel(); val current = ++generation
        val previous = stable ?: presentation
        stable = previous
        presentation = previous.copy(state = LibraryVisualState.scanning); errorKey = null
        pending = scope.launch {
            try {
                val next = acquire()
                coroutineContext.ensureActive()
                if (next == null) { if (generation == current) presentation = previous; return@launch }
                val files = scanner.scan(next.root, next.rootId, next.record.scanSubfolders)
                coroutineContext.ensureActive()
                if (closed || current != generation) return@launch
                fun compare(a: String, b: String) = java.util.Arrays.compareUnsigned(a.toByteArray(Charsets.UTF_8), b.toByteArray(Charsets.UTF_8))
                val rows = files.sortedWith { a, b -> compare(a.title.lowercase(), b.title.lowercase()).takeIf { it != 0 } ?: compare(a.relativePath, b.relativePath) }
                    .map { LibraryEntry(it.id, it.title, it.file.toString()) }
                val selected = listOfNotNull(previous.selectedID, savedSelection).firstOrNull { id -> rows.any { it.id == id } } ?: rows.firstOrNull()?.id
                grant = next
                catalog = files.associateBy { it.id }
                presentation = LibraryPresentation(if (rows.isEmpty()) LibraryVisualState.empty else LibraryVisualState.selected,
                    rows, selected, setOf("chooseFolder", "rescan", "search", "selectMovie", "openSettings"))
                stable = presentation
                try { storage { store.write(next.record) } }
                catch (_: CancellationException) { }
                catch (_: Exception) { if (current == generation) errorKey = "librarySaveFailed" }
            } catch (_: CancellationException) { }
            catch (_: Exception) { if (!closed && current == generation) { presentation = previous; errorKey = "libraryUnavailable" } }
        }
    }
}
