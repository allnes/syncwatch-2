import java.nio.file.Path
import java.util.concurrent.atomic.AtomicInteger
import androidx.collection.ArrayMap
import androidx.collection.MutableScatterMap
import androidx.compose.runtime.*
import androidx.compose.runtime.retain.*
import androidx.compose.runtime.snapshots.Snapshot
import androidx.compose.runtime.snapshots.SnapshotApplyResult
import kotlinx.coroutines.*

private class Node(val id: Int, var value: Int = 0) { val children = mutableListOf<Node>() }
private class Tree(root: Node) : AbstractApplier<Node>(root) {
    override fun insertTopDown(index: Int, instance: Node) { current.children.add(index, instance) }
    override fun insertBottomUp(index: Int, instance: Node) {}
    override fun remove(index: Int, count: Int) { current.children.remove(index, count) }
    override fun move(from: Int, to: Int, count: Int) { current.children.move(from, to, count) }
    override fun onClear() { root.children.clear() }
}
private class Token : RetainObserver {
    val events = mutableListOf<String>()
    override fun onRetained() { events += "retained" }
    override fun onEnteredComposition() { events += "entered" }
    override fun onExitedComposition() { events += "exited" }
    override fun onRetired() { events += "retired" }
    override fun onUnused() { events += "unused" }
}
private class Clock : MonotonicFrameClock {
    private var frame = 0L
    override suspend fun <R> withFrameNanos(onFrame: (Long) -> R): R = onFrame(++frame * 1_000_000L)
}

@Composable private fun Content(order: List<Int>, value: Int, created: AtomicInteger, disposed: AtomicInteger) {
    for (id in order) key(id) {
        remember { created.incrementAndGet() }
        ComposeNode<Node, Tree>(factory = { Node(id) }, update = { set(value + id) { this.value = it } })
        DisposableEffect(id) { onDispose { disposed.incrementAndGet() } }
    }
}

/** Real compiler-transformed composition and snapshots, without a desktop renderer. */
fun main(arguments: Array<String>) = runBlocking {
    val types = listOf(kotlin.Unit::class.java, org.jetbrains.annotations.NotNull::class.java,
        kotlinx.atomicfu.AtomicInt::class.java, kotlinx.coroutines.Job::class.java,
        org.jspecify.annotations.Nullable::class.java, androidx.annotation.IntRange::class.java,
        ArrayMap::class.java, Immutable::class.java, Composer::class.java, RetainedValuesStore::class.java)
    check(arguments.size == types.size)
    types.zip(arguments).forEach { (type, expected) ->
        val origin = Path.of(type.protectionDomain.codeSource.location.toURI()).toRealPath()
        check(origin == Path.of(expected).toRealPath()) { "Unexpected library origin: $origin" }
    }
    val transformed = Class.forName("ComposeRuntimeConsumerKt").declaredMethods.single { it.name == "Content" }
    check(transformed.parameterTypes.any { it == Composer::class.java }) { "Missing Compose compiler transformation" }
    val map = ArrayMap<String, Int>()
    map["room"] = 7
    check(map["room"] == 7 && map.remove("room") == 7 && map.isEmpty())
    val scatter = MutableScatterMap<Int, String>()
    repeat(1000) { scatter[it] = "movie-$it" }
    repeat(500) { check(scatter.remove(it) == "movie-$it") }
    check(scatter.size == 500 && scatter[999] == "movie-999")
    val conflict = mutableStateOf(0)
    val first = Snapshot.takeMutableSnapshot()
    val second = Snapshot.takeMutableSnapshot()
    try {
        first.enter { conflict.value = 1 }
        second.enter { conflict.value = 2 }
        check(first.apply() is SnapshotApplyResult.Success)
        check(second.apply() is SnapshotApplyResult.Failure)
        check(conflict.value == 1)
    } finally { second.dispose(); first.dispose() }
    withTimeout(20_000) {
        val recomposer = Recomposer(coroutineContext)
        try {
            val runner = launch(Clock(), start = CoroutineStart.UNDISPATCHED) { recomposer.runRecomposeAndApplyChanges() }
            val order = mutableStateOf(listOf(1, 2))
            val value = mutableStateOf(0)
            val created = AtomicInteger()
            val disposed = AtomicInteger()
            val tokens = mutableListOf<Token>()
            val store = ManagedRetainedValuesStore()
            store.enableRetainingExitedValues()
            var latest: Token? = null
            var applied = CompletableDeferred<Unit>()
            val content: @Composable () -> Unit = {
                LocalRetainedValuesStoreProvider(store) {
                    val token = retain { Token().also { tokens += it } }
                    SideEffect { latest = token; applied.complete(Unit) }
                    Content(order.value, value.value, created, disposed)
                }
            }
            val root = Node(-1)
            val composition = Composition(Tree(root), recomposer)
            composition.setContent(content)
            check(root.children.map { it.id } == listOf(1, 2) && created.get() == 2)
            applied = CompletableDeferred()
            Snapshot.withMutableSnapshot { order.value = listOf(2, 1, 3); value.value = 10 }
            Snapshot.sendApplyNotifications()
            // Observe application of this content before inspecting its node tree.
            applied.await()
            check(root.children.map { it.id } == listOf(2, 1, 3)) { "Observed children: ${root.children.map { it.id }}" }
            check(root.children.map { it.value } == listOf(12, 11, 13) && created.get() == 3)
            applied = CompletableDeferred()
            Snapshot.withMutableSnapshot { order.value = listOf(3, 2) }
            Snapshot.sendApplyNotifications()
            applied.await()
            check(root.children.map { it.id } == listOf(3, 2) && disposed.get() == 1)
            val token = latest!!
            composition.dispose()
            check(root.children.isEmpty() && disposed.get() == 3)
            check("exited" in token.events && "retired" !in token.events)
            val restoredRoot = Node(-1)
            val restored = Composition(Tree(restoredRoot), recomposer)
            applied = CompletableDeferred()
            restored.setContent(content)
            applied.await()
            check(latest === token && tokens.size == 1 && restoredRoot.children.map { it.id } == listOf(3, 2))
            store.disableRetainingExitedValues()
            restored.dispose()
            store.dispose()
            check(token.events.count { it == "retired" } == 1)
            recomposer.close()
            runner.join()
            check(recomposer.currentState.value == Recomposer.State.ShutDown)
        } finally { recomposer.cancel() }
    }
    println("SYNCWATCH_COMPOSE_RUNTIME_OK: owned origins, compiler transformation, Java/Kotlin collections, snapshot conflict, keyed updates, remember/disposal, retained ownership and recomposer shutdown; GUI not exercised")
}
