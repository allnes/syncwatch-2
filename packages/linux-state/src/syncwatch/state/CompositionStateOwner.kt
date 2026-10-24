package syncwatch.state

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.saveable.LocalSaveableStateRegistry
import androidx.compose.runtime.saveable.SaveableStateRegistry
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleRegistry
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.savedstate.SavedState
import androidx.savedstate.SavedStateRegistryController
import androidx.savedstate.SavedStateRegistryOwner
import androidx.savedstate.compose.LocalSavedStateRegistryOwner
import androidx.savedstate.savedState
import javax.swing.SwingUtilities

/** In-process composition recreation state. Durable domain preferences use LocalStateStore. */
class CompositionSnapshot internal constructor(
    internal val registry: SavedState,
    internal val remembered: Map<String, List<Any?>>,
)

/** One native window owns this object and must dispose its compositions before closing it.
 * The host controls lifecycle transitions; composition providers never own the window lifetime.
 */
class CompositionStateOwner(
    snapshot: CompositionSnapshot? = null,
    canBeSaved: (Any) -> Boolean,
) : SavedStateRegistryOwner, AutoCloseable {
    init { requireEventThread() }
    private val lifecycleRegistry = LifecycleRegistry(this)
    private val controller = SavedStateRegistryController.create(this)
    private var closed = false
    override val lifecycle: Lifecycle get() = lifecycleRegistry
    override val savedStateRegistry get() = controller.savedStateRegistry
    val rememberedState = SaveableStateRegistry(snapshot?.remembered, canBeSaved)

    init {
        controller.performAttach()
        controller.performRestore(snapshot?.registry)
        lifecycleRegistry.handleLifecycleEvent(Lifecycle.Event.ON_CREATE)
    }

    fun resume() {
        requireOpen()
        lifecycleRegistry.handleLifecycleEvent(Lifecycle.Event.ON_RESUME)
    }

    fun stop() {
        requireOpen()
        lifecycleRegistry.currentState = Lifecycle.State.CREATED
    }

    /** Save while the composition and its providers are still alive. No disk format is introduced. */
    fun snapshot(): CompositionSnapshot {
        requireOpen()
        val state = savedState()
        controller.performSave(state)
        return CompositionSnapshot(state, rememberedState.performSave().mapValues { (_, values) -> values.toList() })
    }

    override fun close() {
        requireEventThread()
        if (closed) return
        lifecycleRegistry.handleLifecycleEvent(Lifecycle.Event.ON_DESTROY)
        closed = true
    }

    private fun requireOpen() {
        requireEventThread()
        check(!closed) { "The window state owner is closed" }
    }

    private fun requireEventThread() {
        check(SwingUtilities.isEventDispatchThread()) { "Window state requires the Swing event thread" }
    }
}

@Composable
fun ProvideCompositionState(owner: CompositionStateOwner, content: @Composable () -> Unit) {
    CompositionLocalProvider(
        LocalLifecycleOwner provides owner,
        LocalSavedStateRegistryOwner provides owner,
        LocalSaveableStateRegistry provides owner.rememberedState,
        content = content,
    )
}
