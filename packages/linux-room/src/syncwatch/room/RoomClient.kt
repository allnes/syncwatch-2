package syncwatch.room

import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.net.http.WebSocket
import java.time.Duration
import java.util.concurrent.CompletableFuture
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.*

/** One room attempt owns all network work; close cancels and joins it. */
class RoomClient(val address: RoomAddress) {
    private val client = HttpClient.newBuilder().followRedirects(HttpClient.Redirect.NEVER).connectTimeout(Duration.ofSeconds(10)).build()
    private val gate = Any()
    private val requests = mutableSetOf<CompletableFuture<HttpResponse<ByteArray>>>()
    private var eventStream: RoomEventStream? = null
    private var eventConnection: CompletableFuture<WebSocket>? = null
    private var closing: CompletableDeferred<Unit>? = null
    suspend fun create(identity: RoomIdentity, connection: RoomConnection, creationKey: RoomSecret): RoomAdmission {
        val body = RoomWire.encode(mapOf("v" to 1L, "clientRunId" to identity.clientRunId, "syncplayUsername" to identity.syncplayUsername,
            "syncplayHost" to connection.host, "syncplayPort" to connection.port, "syncplayRoom" to connection.room))
        return RoomAdmission.decode(request("POST", "v1/rooms", creationKey, body), identity, true)
    }
    suspend fun join(roomId: String, invitation: RoomSecret, identity: RoomIdentity): RoomAdmission {
        RoomWire.id(roomId)
        val body = RoomWire.encode(mapOf("v" to 1L, "invitation" to invitation.value, "clientRunId" to identity.clientRunId, "syncplayUsername" to identity.syncplayUsername))
        return RoomAdmission.decode(request("POST", "v1/rooms/$roomId/join", body = body), identity, false)
    }
    suspend fun snapshot(admission: RoomAdmission): RoomBootstrap = RoomBootstrap.decode(request("GET", "v1/rooms/${admission.roomId}/snapshot", admission.token))
    suspend fun leave(admission: RoomAdmission) {
        val value = RoomWire.parse(request("POST", "v1/rooms/${admission.roomId}/leave", admission.token))
        RoomWire.keys(value, "v", "status")
        if (RoomWire.integer(value["v"], 1) != 1L || value["status"] != "left") throw RoomWire.bad()
    }
    /** Attach immediately after admission, before hashing media. */
    suspend fun openEvents(admission: RoomAdmission): RoomEventStream {
        currentCoroutineContext().ensureActive()
        val stream = RoomEventStream()
        val uri = address.endpoint("v1/rooms/${admission.roomId}/events")
        val events = java.net.URI(if (uri.scheme == "https") "wss" else "ws", uri.rawAuthority, uri.rawPath, null, null)
        val future = synchronized(gate) {
            if (closing != null || eventStream != null) throw RoomProtocolException("closed")
            eventStream = stream
            client.newWebSocketBuilder().header("Authorization", "Bearer ${admission.token.value}")
                .connectTimeout(Duration.ofSeconds(20)).buildAsync(events, stream).also { eventConnection = it }
        }
        try {
            future.awaitRoom()
            currentCoroutineContext().ensureActive()
            synchronized(gate) { if (closing != null) throw RoomProtocolException("closed") }
            return stream
        } catch (error: Exception) { future.cancel(true); stream.close(); throw error }
    }
    suspend fun close() = withContext(NonCancellable + Dispatchers.IO) {
        var leader = false
        val completion = synchronized(gate) { closing ?: CompletableDeferred<Unit>().also { closing = it; leader = true } }
        if (leader) {
            try {
                val pending = synchronized(gate) { requests.toList() }
                pending.forEach { it.cancel(true) }
                eventConnection?.cancel(true); eventStream?.close()
                client.shutdownNow()
                if (!client.awaitTermination(Duration.ofSeconds(5))) throw RoomProtocolException("transport")
                completion.complete(Unit)
            } catch (_: Exception) { completion.completeExceptionally(RoomProtocolException("transport")) }
        }
        completion.await()
    }
    private suspend fun request(method: String, path: String, credential: RoomSecret? = null, body: ByteArray? = null): ByteArray {
        currentCoroutineContext().ensureActive()
        val builder = HttpRequest.newBuilder(address.endpoint(path)).timeout(Duration.ofSeconds(20)).header("Accept", "application/json")
        credential?.let { builder.header("Authorization", "Bearer ${it.value}") }
        if (body != null) builder.header("Content-Type", "application/json")
        val request = builder.method(method, body?.let(HttpRequest.BodyPublishers::ofByteArray) ?: HttpRequest.BodyPublishers.noBody()).build()
        val future = synchronized(gate) {
            if (closing != null) throw RoomProtocolException("closed")
            client.sendAsync(request) { info -> RoomBodySubscriber(info.headers().firstValueAsLong("Content-Length").orElse(-1)) }
                .also { requests.add(it) }
        }
        try {
            val response = future.awaitRoom()
            currentCoroutineContext().ensureActive()
            if (response.uri() != request.uri() || response.headers().firstValue("Content-Type").orElse("").substringBefore(';').trim().lowercase() != "application/json")
                throw RoomProtocolException("transport")
            val bytes = response.body()
            if (response.statusCode() !in 200..299) {
                val value = RoomWire.parse(bytes); RoomWire.keys(value, "error")
                val error = RoomWire.obj(value["error"]); RoomWire.keys(error, "code"); val code = RoomWire.string(error["code"])
                val allowed = setOf("unauthorized", "forbidden", "notFound", "conflict", "expired", "queueFull", "tlsRequired", "malformed", "frameTooLarge", "internal")
                throw RoomProtocolException(if (code in allowed) code else "transport")
            }
            return bytes
        } finally { synchronized(gate) { requests.remove(future) } }
    }
}
private suspend fun <T> CompletableFuture<T>.awaitRoom(): T = suspendCancellableCoroutine { continuation ->
    whenComplete { value, error ->
        if (error != null) continuation.resumeWithException(error) else continuation.resume(value)
    }
    continuation.invokeOnCancellation { cancel(true) }
}
