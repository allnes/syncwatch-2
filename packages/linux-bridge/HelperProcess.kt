package syncwatch.bridge

import java.io.ByteArrayOutputStream
import java.io.EOFException
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.file.Path
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.CompletableFuture
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Owns inherited pipes only. Compose and playback state are separate consumers. */
class HelperProcess private constructor(private val process: Process) : HelperTransport {
    val processID: Long get() = process.pid()
    private val closed = AtomicBoolean(false)
    private val reading = AtomicBoolean(false)
    private val writing = AtomicBoolean(false)
    private val reader = worker("syncwatch-helper-read")
    private val writer = worker("syncwatch-helper-write")

    init {
        Thread({
            try {
                val discard = ByteArray(1024)
                while (process.errorStream.read(discard) >= 0) { }
            } catch (_: IOException) { }
        }, "syncwatch-helper-diagnostics").apply { isDaemon = true; start() }
    }

    override fun read(): CompletableFuture<ByteArray> = submit(reader, reading) {
        val frame = ByteArrayOutputStream()
        while (true) {
            val byte = process.inputStream.read()
            if (byte < 0) throw EOFException("Helper stopped")
            frame.write(byte)
            if (frame.size() > MAX_FRAME_BYTES) throw IOException("frameTooLarge")
            if (byte == 10) break
        }
        frame.toByteArray().also(::validate)
    }

    override fun send(frame: ByteArray): CompletableFuture<Unit> {
        validate(frame)
        val owned = frame.copyOf()
        return submit(writer, writing) {
            process.outputStream.write(owned)
            process.outputStream.flush()
        }
    }

    private fun <T> submit(executor: ThreadPoolExecutor, busy: AtomicBoolean, work: () -> T): CompletableFuture<T> {
        val result = CompletableFuture<T>()
        if (closed.get() || !busy.compareAndSet(false, true)) {
            result.completeExceptionally(IOException("queueFull"))
            return result
        }
        result.whenComplete { _, _ -> if (result.isCancelled) process.destroyForcibly() }
        try {
            executor.execute {
                try {
                    val value = work()
                    busy.set(false)
                    result.complete(value)
                } catch (error: Exception) {
                    busy.set(false)
                    process.destroyForcibly()
                    result.completeExceptionally(error)
                }
            }
        } catch (error: RejectedExecutionException) {
            busy.set(false)
            result.completeExceptionally(error)
        }
        return result
    }

    /** Invoke on the resource owner's worker, never during Compose rendering. */
    override fun close() {
        if (!closed.compareAndSet(false, true)) return
        // Close/blocked writes are released by the bounded watchdog.
        val watchdog = Thread({
            if (!process.waitFor(3, TimeUnit.SECONDS)) process.destroyForcibly()
        }, "syncwatch-helper-close").apply { isDaemon = true; start() }
        try { process.outputStream.close() } catch (_: IOException) { }
        process.waitFor()
        watchdog.join()
        reader.shutdown()
        writer.shutdown()
        process.inputStream.close()
        process.errorStream.close()
    }

    companion object {
        private const val MAX_FRAME_BYTES = 65536 // contracts/manifest.json, including LF

        fun start(executable: Path, runtime: Path): HelperProcess {
            require(executable.isAbsolute && runtime.isAbsolute)
            val builder = ProcessBuilder(executable.toString(), runtime.toString()).directory(runtime.toFile())
            builder.environment().keys.removeIf { it.uppercase().startsWith("PYTHON") }
            return HelperProcess(builder.start())
        }

        private fun worker(name: String) = ThreadPoolExecutor(
            1, 1, 0, TimeUnit.SECONDS, ArrayBlockingQueue(1),
            { task -> Thread(task, name).apply { isDaemon = true } }, ThreadPoolExecutor.AbortPolicy(),
        )

        private fun validate(frame: ByteArray) {
            if (frame.size !in 2..MAX_FRAME_BYTES || frame.last() != 10.toByte() ||
                frame.dropLast(1).contains(10.toByte()) || frame.contains(13.toByte())) throw IOException("malformed")
            Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(frame))
        }
    }
}
