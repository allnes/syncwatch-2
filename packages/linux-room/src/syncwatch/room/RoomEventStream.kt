package syncwatch.room

import java.net.http.WebSocket
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.nio.charset.StandardCharsets
import java.util.concurrent.CompletionStage
import kotlinx.coroutines.channels.Channel

/** Bounded single-consumer stream. Decode each message before applying it. */
class RoomEventStream internal constructor() : WebSocket.Listener {
    private val messages = Channel<ByteArray>(32)
    private val gate = Any()
    private val text = StringBuilder()
    private var socket: WebSocket? = null
    private var closed = false
    private var receiving = false
    override fun onOpen(webSocket: WebSocket) {
        synchronized(gate) {
            if (closed) { webSocket.abort(); return }
            socket = webSocket
        }
        webSocket.request(1)
    }
    override fun onText(webSocket: WebSocket, data: CharSequence, last: Boolean): CompletionStage<*>? {
        try {
            synchronized(gate) {
                if (closed) return null
                if (data.length > RoomWire.maximumBytes - text.length) throw RoomProtocolException("frameTooLarge")
                text.append(data)
                if (last) {
                    val buffer = StandardCharsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT).encode(CharBuffer.wrap(text))
                    val bytes = ByteArray(buffer.remaining()); buffer.get(bytes)
                    RoomWire.parse(bytes)
                    if (!messages.trySend(bytes).isSuccess) throw RoomProtocolException("queueFull")
                    text.setLength(0)
                }
            }
            webSocket.request(1)
        } catch (error: RoomProtocolException) { finish(error) }
        catch (_: Exception) { finish(RoomProtocolException("malformed")) }
        return null
    }
    override fun onBinary(webSocket: WebSocket, data: java.nio.ByteBuffer, last: Boolean): CompletionStage<*>? {
        finish(RoomProtocolException("malformed")); return null
    }
    override fun onClose(webSocket: WebSocket, statusCode: Int, reason: String): CompletionStage<*>? {
        finish(RoomProtocolException("closed")); return null
    }
    override fun onError(webSocket: WebSocket, error: Throwable) { finish(RoomProtocolException("transport")) }
    suspend fun receive(): ByteArray {
        synchronized(gate) { if (receiving) throw RoomProtocolException("malformed"); receiving = true }
        try { return messages.receive() } finally { synchronized(gate) { receiving = false } }
    }
    fun close() { finish(RoomProtocolException("closed")); while (messages.tryReceive().isSuccess) { } }
    private fun finish(error: RoomProtocolException) {
        synchronized(gate) {
            if (closed) return
            closed = true; text.setLength(0); socket?.abort(); messages.close(error)
        }
    }
}
