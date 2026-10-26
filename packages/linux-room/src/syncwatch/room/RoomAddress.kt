package syncwatch.room

import java.net.URI

class RoomProtocolException(val code: String) : java.io.IOException(code)

/** Service origin only; credentials never occur in a URL. */
class RoomAddress(value: String) {
    val origin: URI
    init {
        val uri = try { URI(value) } catch (_: Exception) { throw RoomProtocolException("invalidRoomService") }
        if (!value.matches(Regex("https?://([A-Za-z0-9.-]+|\\[[0-9A-Fa-f:]+\\])(?::[0-9]{1,5})?/?")) || value.any { it.code <= 32 || it.code == 127 } || '\\' in value || uri.rawUserInfo != null || uri.rawQuery != null || uri.rawFragment != null ||
            uri.rawPath !in listOf("", "/") || uri.host.isNullOrEmpty() || uri.port !in -1..65535 || uri.port == 0 ||
            !(uri.scheme == "https" || uri.scheme == "http" && uri.host in listOf("127.0.0.1", "[::1]", "::1")))
            throw RoomProtocolException("invalidRoomService")
        origin = uri
    }
    internal fun endpoint(path: String): URI = origin.resolve("/$path")
    override fun toString(): String = origin.toASCIIString()
}

/** Memory-only credential; logging it does not disclose its value. */
class RoomSecret internal constructor(internal val value: String) {
    init {
        if (value.length !in 32..256 || value.any { it.code !in 33..126 }) throw RoomProtocolException("invalidRoomCredential")
    }
    override fun toString(): String = "[redacted]"
    // Expose plaintext only for an explicit invitation transfer.
    fun copyInvitation(): String = value
    companion object { fun fromInput(value: String) = RoomSecret(value) }
}
