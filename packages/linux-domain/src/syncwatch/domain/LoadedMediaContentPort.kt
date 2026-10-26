package syncwatch.domain

/** Local equality evidence. Never include the opaque stamp in room DTOs or logs. */
class LoadedMediaVersion(val scope: PlaybackScope, val sizeBytes: Long, private val stamp: String) {
    init {
        if (sizeBytes < 0 || stamp.length != 128 || stamp.any { it !in '0'..'9' && it !in 'a'..'f' })
            throw WatchFailure("malformed")
    }
    override fun equals(other: Any?): Boolean = other is LoadedMediaVersion &&
        scope == other.scope && sizeBytes == other.sizeBytes && stamp == other.stamp
    override fun hashCode(): Int = 31 * (31 * scope.hashCode() + sizeBytes.hashCode()) + stamp.hashCode()
    override fun toString(): String = "LoadedMediaVersion(redacted)"
}

/** Reads the player's owned input without resolving another path or moving its stream. */
interface LoadedMediaContentPort {
    suspend fun contentVersion(scope: PlaybackScope): LoadedMediaVersion
    suspend fun readContent(offset: Long, capacity: Int, scope: PlaybackScope): ByteArray
}
