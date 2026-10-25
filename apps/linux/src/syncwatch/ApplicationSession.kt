package syncwatch

import java.nio.file.Path
import kotlinx.coroutines.*
import syncwatch.domain.FileLocalStateStore
import syncwatch.library.FileLibraryAccessStore
import syncwatch.playback.X11Display

/** One normal desktop window owns its independent library, watch and local-state services. */
internal class ApplicationSession(media: MediaConfiguration, display: X11Display?, private val work: CoroutineScope,
    statePath: Path = AppearancePreferences.defaultPath()) {
    val preferences = AppearancePreferences(FileLocalStateStore(statePath))
    val library = LibraryController(FileLibraryAccessStore(statePath.resolveSibling("library-access.json")), work,
        preferences.state.selectedMediaId)
    val watch = WatchSessionCoordinator(preferences, media, display, work)
    private var closing: Job? = null
    fun requestClose(onClosed: () -> Unit) {
        if (closing?.isActive == true) return
        closing = work.launch {
            try { watch.close(); library.close(); onClosed() }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { /* The watch owner exposes the close failure and retains the window. */ }
        }
    }
}
