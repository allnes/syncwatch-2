import java.nio.file.Path
import kotlinx.atomicfu.atomic
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.future.asCompletableFuture
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** Exercise scheduling, synchronization, cancellation and the rebuilt debug agent. */
fun main(arguments: Array<String>) = runBlocking {
    check(arguments.size == 5)
    val origins = listOf(kotlin.Unit::class.java, org.jetbrains.annotations.NotNull::class.java,
        kotlinx.atomicfu.AtomicInt::class.java, kotlinx.coroutines.Job::class.java)
    origins.zip(arguments.take(4)).forEach { (type, expected) ->
        val observed = Path.of(type.protectionDomain.codeSource.location.toURI()).toRealPath()
        check(observed == Path.of(expected).toRealPath()) { "Unexpected runtime origin: $observed" }
    }
    val installedType = Class.forName("kotlinx.coroutines.debug.internal.AgentInstallationType")
    val installedGetter = installedType.declaredMethods.single { it.name.startsWith("isInstalledStatically") && it.parameterCount == 0 }
    val installed = installedGetter.invoke(installedType.getField("INSTANCE").get(null))
    check(installed == (arguments.last() == "agent"))
    withTimeout(20_000) {
        val count = atomic(0)
        val mutex = Mutex()
        var protectedCount = 0
        coroutineScope {
            repeat(4) {
                launch(Dispatchers.Default) {
                    repeat(4096) { count.incrementAndGet(); mutex.withLock { protectedCount++ } }
                }
            }
        }
        check(count.value == 16384 && protectedCount == 16384)
        check(count.compareAndSet(16384, 7) && !count.compareAndSet(16384, 9))
        val reference = atomic<String?>(null)
        check(reference.compareAndSet(null, "movie"))
        check(reference.getAndSet("room") == "movie" && reference.value == "room")
        val flag = atomic(false)
        check(flag.compareAndSet(false, true) && flag.value)
        val long = atomic(Long.MAX_VALUE)
        check(long.getAndSet(Long.MIN_VALUE) == Long.MAX_VALUE && long.value == Long.MIN_VALUE)
        val channel = Channel<Int>(7)
        val producer = launch(Dispatchers.Default) { repeat(1000) { channel.send(it) }; channel.close() }
        var sum = 0L
        for (value in channel) sum += value
        producer.join()
        check(sum == 499500L)
        val state = MutableStateFlow(0)
        val observed = mutableListOf<Int>()
        val collector = launch(start = CoroutineStart.UNDISPATCHED) { state.take(2).toList(observed) }
        state.value = 1
        collector.join()
        check(observed == listOf(0, 1))
        val entered = CompletableDeferred<Unit>()
        val released = CompletableDeferred<Unit>()
        val owned = launch(Dispatchers.Default) {
            try { entered.complete(Unit); awaitCancellation() }
            finally { released.complete(Unit) }
        }
        entered.await()
        owned.cancelAndJoin()
        check(released.isCompleted && owned.isCancelled)
        supervisorScope {
            val failed = async { throw IllegalArgumentException("expected consumer failure") }
            try { failed.await(); error("Missing failure") }
            catch (expected: IllegalArgumentException) { check(expected.message == "expected consumer failure") }
            check(isActive)
        }
        check(CompletableDeferred(42).asCompletableFuture().get() == 42)
    }
    println("SYNCWATCH_CONCURRENCY_OK ${arguments.last()}: owned runtime origins, atomics, scheduling, mutex, channels, flow, cancellation, failure and futures")
}
