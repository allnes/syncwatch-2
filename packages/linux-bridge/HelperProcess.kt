package syncwatch.bridge

import java.nio.file.Path
import java.util.concurrent.CompletableFuture

/** Kotlin facade over the bounded JVM pipe owner. Invoke close on the resource
 * owner's worker. This facade and Compose remain source-only until L01 closes.
 */
class HelperProcess private constructor(private val transport: PipeTransport) : AutoCloseable {
    fun read(): CompletableFuture<ByteArray> = transport.read()
    fun send(frame: ByteArray): CompletableFuture<Unit> = transport.send(frame).thenApply { Unit }
    override fun close() { transport.closeAsync().join() }

    companion object {
        fun start(executable: Path, runtime: Path): HelperProcess = HelperProcess(PipeTransport.start(executable, runtime))
    }
}
