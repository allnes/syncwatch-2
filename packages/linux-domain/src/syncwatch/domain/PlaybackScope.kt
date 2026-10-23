package syncwatch.domain

import java.util.UUID

class WatchFailure(val code: String) : IllegalArgumentException(code)

/** Domain ownership only; no Compose, native player or helper type enters this value. */
data class PlaybackScope(val clientRunId: String, val mediaGeneration: Long) {
    init {
        if (!clientRunId.matches(Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,63}")) || mediaGeneration !in 0..MAXIMUM_GENERATION) {
            throw WatchFailure("malformed")
        }
    }
    fun check(owner: PlaybackScope) {
        if (owner.clientRunId != clientRunId) throw WatchFailure("foreignRun")
        if (owner.mediaGeneration != mediaGeneration) throw WatchFailure("staleGeneration")
    }
    fun replacingMedia(): PlaybackScope {
        if (mediaGeneration == MAXIMUM_GENERATION) throw WatchFailure("malformed")
        return copy(mediaGeneration = mediaGeneration + 1)
    }
    companion object {
        const val MAXIMUM_GENERATION = 9_007_199_254_740_991L
        fun fresh() = PlaybackScope(UUID.randomUUID().toString(), 0)
        fun validateId(id: String) { PlaybackScope(id, 0) }
    }
}
