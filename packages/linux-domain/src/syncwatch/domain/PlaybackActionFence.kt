package syncwatch.domain

enum class CorrectionDisposition { apply, waitForUserObservation, cancelled, unavailable }

/** Native ordering only. Syncplay retains timing policy; the owner serializes access. */
class PlaybackActionFence(val scope: PlaybackScope) {
    var issuedSequence = 0L
        private set
    var publishedSequence = 0L
        private set
    var invalidated = false
        private set
    fun beginUserAction(owner: PlaybackScope): Long {
        checkOwner(owner)
        if (issuedSequence == PlaybackScope.MAXIMUM_GENERATION) throw WatchFailure("malformed")
        return ++issuedSequence
    }
    /** Recheck on the serialized writer immediately before emitting a user frame. */
    fun canPublish(sequence: Long, owner: PlaybackScope): Boolean {
        checkOwner(owner)
        if (sequence !in 1..issuedSequence) throw WatchFailure("malformed")
        return sequence > publishedSequence
    }
    fun didPublish(sequence: Long, observation: PlaybackObservation): Boolean {
        if (!canPublish(sequence, observation.scope)) return false
        if (observation.status != PlaybackStatus.ready) throw WatchFailure("invalidState")
        publishedSequence = sequence
        return true
    }
    /** Check before queuing a correction and after its native await. A cancelled
     * reply must follow the newer actual user frame, not merely the local request.
     */
    fun correction(owner: PlaybackScope, afterUserAction: Long): CorrectionDisposition {
        scope.check(owner)
        if (invalidated) return CorrectionDisposition.unavailable
        if (afterUserAction !in 0..publishedSequence) throw WatchFailure("malformed")
        if (afterUserAction < publishedSequence) return CorrectionDisposition.cancelled
        return if (issuedSequence == publishedSequence) CorrectionDisposition.apply else CorrectionDisposition.waitForUserObservation
    }
    fun invalidate() { invalidated = true }
    private fun checkOwner(owner: PlaybackScope) {
        scope.check(owner)
        if (invalidated) throw WatchFailure("invalidState")
    }
}
