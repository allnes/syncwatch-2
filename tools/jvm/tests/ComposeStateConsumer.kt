import java.nio.file.Path
import javax.swing.SwingUtilities
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.*
import androidx.compose.runtime.snapshots.Snapshot
import androidx.lifecycle.*
import androidx.lifecycle.compose.*
import androidx.savedstate.*
import androidx.savedstate.compose.LocalSavedStateRegistryOwner
import androidx.savedstate.serialization.*
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.swing.*
import kotlinx.serialization.Serializable
import syncwatch.state.*

@Serializable
private data class WindowModel(val room: String, val tracks: List<String>, val position: Long)

private class EmptyTree : AbstractApplier<Unit>(Unit) {
    override fun insertTopDown(index: Int, instance: Unit) = error("No renderer in this consumer")
    override fun insertBottomUp(index: Int, instance: Unit) = error("No renderer in this consumer")
    override fun remove(index: Int, count: Int) = error("No renderer in this consumer")
    override fun move(from: Int, to: Int, count: Int) = error("No renderer in this consumer")
    override fun onClear() {}
}

private class Clock : MonotonicFrameClock {
    private var frame = 0L
    override suspend fun <R> withFrameNanos(onFrame: (Long) -> R): R = onFrame(++frame * 1_000_000L)
}

private data class Applied(val count: Int, val model: WindowModel, val movie: String, val lifecycle: Lifecycle.State)
private class Screen {
    val flow = MutableStateFlow("Кино 映画 – initial")
    val applied = Channel<Applied>(Channel.UNLIMITED)
    lateinit var count: MutableState<Int>
    var counterInitializations = 0
    var modelInitializations = 0
    var disposed = 0

    @Composable fun Content(owner: CompositionStateOwner, model: WindowModel) {
        ProvideCompositionState(owner) {
            check(LocalLifecycleOwner.current === owner)
            check(LocalSavedStateRegistryOwner.current === owner)
            check(LocalSaveableStateRegistry.current === owner.rememberedState)
            val counter = rememberSaveable(saver = Saver<MutableState<Int>, Int>(
                save = { it.value }, restore = { mutableStateOf(it) },
            )) { counterInitializations++; mutableStateOf(3) }
            val restored = rememberSerializable(serializer = WindowModel.serializer()) { modelInitializations++; model }
            val movie by flow.collectAsStateWithLifecycle()
            val lifecycle by owner.lifecycle.currentStateAsState()
            val observation = Applied(counter.value, restored, movie, lifecycle)
            SideEffect { count = counter; check(applied.trySend(observation).isSuccess) }
            DisposableEffect(Unit) { onDispose { disposed++ } }
        }
    }

    suspend fun await(predicate: (Applied) -> Boolean): Applied {
        while (true) { val value = applied.receive(); if (predicate(value)) return value }
    }

    fun composition(recomposer: Recomposer, owner: CompositionStateOwner, model: WindowModel): Composition =
        Composition(EmptyTree(), recomposer).also { it.setContent { Content(owner, model) } }
}

/** Exercises the real app state owner on the Swing EDT, without creating a window. */
@OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
fun main(arguments: Array<String>) = runBlocking {
    val types = listOf(kotlin.Unit::class.java, org.jetbrains.annotations.NotNull::class.java,
        kotlinx.atomicfu.AtomicInt::class.java, Job::class.java, org.jspecify.annotations.Nullable::class.java,
        androidx.annotation.IntRange::class.java, androidx.collection.ArrayMap::class.java,
        Immutable::class.java, Composer::class.java, androidx.compose.runtime.retain.RetainedValuesStore::class.java,
        androidx.arch.core.internal.SafeIterableMap::class.java, kotlinx.serialization.KSerializer::class.java,
        SwingDispatcher::class.java, Lifecycle::class.java, LifecycleRegistry::class.java,
        Class.forName("androidx.lifecycle.compose.LocalLifecycleOwnerKt"), SavedState::class.java,
        Class.forName("androidx.savedstate.compose.LocalSavedStateRegistryOwnerKt"), SaveableStateRegistry::class.java)
    check(types.size == arguments.size)
    types.zip(arguments).forEach { (type, expected) ->
        val origin = Path.of(type.protectionDomain.codeSource.location.toURI()).toRealPath()
        check(origin == Path.of(expected).toRealPath()) { "Unexpected library origin: $origin" }
    }
    check(!SwingUtilities.isEventDispatchThread())
    check(runCatching { CompositionStateOwner(canBeSaved = { true }) }.exceptionOrNull() is IllegalStateException)
    val model = WindowModel("Комната 映画 🎬", listOf("Русский", "日本語", "English"), 9_876_543_210L)
    check(WindowModel.serializer().descriptor.elementsCount == 3)
    check(decodeFromSavedState(WindowModel.serializer(), encodeToSavedState(WindowModel.serializer(), model)) == model)
    check(Dispatchers.Main.immediate === Dispatchers.Swing.immediate)
    withTimeout(20_000) {
        withContext(Dispatchers.Swing) {
            check(SwingUtilities.isEventDispatchThread())
            val canSave: (Any) -> Boolean = { it is Int || it is String || it is SavedState }
            val owner = CompositionStateOwner(canBeSaved = canSave)
            check(owner.lifecycle.currentState == Lifecycle.State.CREATED)
            withContext(Dispatchers.Default) {
                check(runCatching { owner.resume() }.exceptionOrNull() is IllegalStateException)
                check(runCatching {
                    (owner.lifecycle as LifecycleRegistry).currentState = Lifecycle.State.RESUMED
                }.exceptionOrNull() is IllegalStateException)
            }
            owner.savedStateRegistry.registerSavedStateProvider("window") { savedState { putString("room", model.room) } }
            check(runCatching { owner.savedStateRegistry.registerSavedStateProvider("window") { savedState() } }.exceptionOrNull() is IllegalArgumentException)
            val lifecycleEvents = Channel<String>(Channel.UNLIMITED)
            val repeatJob = launch(start = CoroutineStart.UNDISPATCHED) {
                owner.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
                    lifecycleEvents.send("started")
                    try { awaitCancellation() } finally { check(lifecycleEvents.trySend("stopped").isSuccess) }
                }
            }
            val screen = Screen()
            val recomposer = Recomposer(coroutineContext)
            // A rendered UI supplies its own snapshot pump. Own this headless driver's pump.
            val writes = Channel<Unit>(Channel.CONFLATED)
            val observer = Snapshot.registerGlobalWriteObserver { writes.trySend(Unit) }
            val notifier = launch(start = CoroutineStart.UNDISPATCHED) {
                for (write in writes) Snapshot.sendApplyNotifications()
            }
            var composition: Composition? = null
            var restoredOwner: CompositionStateOwner? = null
            try {
                val runner = launch(Clock(), start = CoroutineStart.UNDISPATCHED) { recomposer.runRecomposeAndApplyChanges() }
                composition = screen.composition(recomposer, owner, model)
                screen.await { it.count == 3 && it.model == model && it.lifecycle == Lifecycle.State.CREATED }
                owner.resume()
                check(lifecycleEvents.receive() == "started")
                screen.flow.subscriptionCount.first { it == 1 }
                screen.await { it.lifecycle == Lifecycle.State.RESUMED }
                Snapshot.withMutableSnapshot { screen.count.value = 42 }
                Snapshot.sendApplyNotifications()
                screen.flow.value = "Кино 映画 – playing"
                screen.await { it.count == 42 && it.movie == screen.flow.value }
                owner.stop()
                check(lifecycleEvents.receive() == "stopped")
                screen.flow.subscriptionCount.first { it == 0 }
                val stopped = screen.await { it.lifecycle == Lifecycle.State.CREATED }
                screen.flow.value = "Кино 映画 – resumed"
                check(stopped.movie == "Кино 映画 – playing")
                owner.resume()
                check(lifecycleEvents.receive() == "started")
                screen.await { it.lifecycle == Lifecycle.State.RESUMED && it.movie == screen.flow.value }
                val snapshot = owner.snapshot()
                composition.dispose()
                composition = null
                owner.close()
                owner.close()
                check(lifecycleEvents.receive() == "stopped")
                repeatJob.join()
                check(repeatJob.isCompleted && !repeatJob.isCancelled)
                check(owner.lifecycle.currentState == Lifecycle.State.DESTROYED)
                check((owner.lifecycle as LifecycleRegistry).observerCount == 0)
                check(runCatching { owner.snapshot() }.exceptionOrNull() is IllegalStateException)
                check(runCatching { owner.resume() }.exceptionOrNull() is IllegalStateException)
                screen.flow.subscriptionCount.first { it == 0 }
                restoredOwner = CompositionStateOwner(snapshot, canSave)
                val registryState = restoredOwner.savedStateRegistry.consumeRestoredStateForKey("window")!!
                check(registryState.read { getString("room") } == model.room)
                check(restoredOwner.savedStateRegistry.consumeRestoredStateForKey("window") == null)
                val nextOwner = restoredOwner
                composition = screen.composition(recomposer, nextOwner, model.copy(room = "Must not initialize"))
                screen.await { it.count == 42 && it.model == model && it.lifecycle == Lifecycle.State.CREATED }
                check(screen.counterInitializations == 1 && screen.modelInitializations == 1)
                nextOwner.resume()
                screen.flow.subscriptionCount.first { it == 1 }
                screen.flow.value = "Restored window"
                screen.await { it.movie == "Restored window" && it.count == 42 && it.model == model }
                composition.dispose()
                composition = null
                nextOwner.close()
                check(screen.disposed == 2)
                screen.flow.subscriptionCount.first { it == 0 }
                check((nextOwner.lifecycle as LifecycleRegistry).observerCount == 0)
                recomposer.close()
                runner.join()
                check(recomposer.currentState.value == Recomposer.State.ShutDown)
            } finally {
                composition?.dispose()
                restoredOwner?.close()
                owner.close()
                recomposer.cancel()
                repeatJob.cancelAndJoin()
                observer.dispose()
                writes.close()
                notifier.cancelAndJoin()
            }
        }
    }
    println("SYNCWATCH_COMPOSE_STATE_OK: 19 owned origins, generated serializer, Unicode nested roundtrip, real Swing/Main EDT, enforced thread affinity, lifecycle stop/restart/destroy, lifecycle-aware flow, actual app owner locals, rememberSaveable/rememberSerializable restoration, provider consumption, observer and recomposer shutdown; no window or renderer exercised")
}
