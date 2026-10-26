package syncwatch.bridge

import java.util.concurrent.CompletableFuture

/** Process I/O has no dependency on the session scheduler or UI toolkit. */
interface HelperTransport : AutoCloseable {
    fun read(): CompletableFuture<ByteArray>
    fun send(frame: ByteArray): CompletableFuture<Unit>
}
