package syncwatch.domain

enum class WatchPhase { idle, selected, preparing, active, ended }
sealed interface WatchEffect {
    data class Load(val scope: PlaybackScope, val mediaId: String, val positionMs: Long) : WatchEffect
    data class Release(val scope: PlaybackScope) : WatchEffect
}

/** Serialize access in the application owner. Effects allocate/release local resources only. */
class WatchSession(localState: LocalState = LocalState(), scope: PlaybackScope = PlaybackScope.fresh()) {
    var localState: LocalState = localState
        private set
    var scope = scope
        private set
    var mediaId = localState.selectedMediaId
        private set
    var phase = if (mediaId == null) WatchPhase.idle else WatchPhase.selected
        private set
    var positionMs = mediaId?.let(localState::resumePositionFor) ?: 0
        private set
    var paused = true
        private set
    var playerPresented = false
        private set
    init { localState.validate() }

    fun select(mediaId: String, restartFromBeginning: Boolean = false): List<WatchEffect> {
        PlaybackScope.validateId(mediaId)
        if (!restartFromBeginning && this.mediaId == mediaId) return emptyList()
        val next = scope.replacingMedia()
        val effects = releaseEffects()
        scope = next; this.mediaId = mediaId; localState = localState.copy(selectedMediaId = mediaId)
        positionMs = if (restartFromBeginning) 0 else localState.resumePositionFor(mediaId)
        if (restartFromBeginning) localState = localState.copy(resumePositions = localState.resumePositions.filterNot { it.mediaId == mediaId })
        phase = WatchPhase.selected; paused = true; playerPresented = false
        return effects
    }
    fun start(): List<WatchEffect> {
        val selected = mediaId ?: throw WatchFailure("invalidState")
        if (phase in setOf(WatchPhase.active, WatchPhase.preparing)) { playerPresented = true; return emptyList() }
        val next = scope.replacingMedia()
        scope = next; phase = WatchPhase.preparing; playerPresented = true; paused = true
        return listOf(WatchEffect.Load(scope, selected, positionMs))
    }
    fun loaded(owner: PlaybackScope) { check(owner, WatchPhase.preparing); phase = WatchPhase.active }
    fun recordPlayback(owner: PlaybackScope, positionMs: Long, durationMs: Long?, paused: Boolean) {
        check(owner, WatchPhase.active)
        if (positionMs !in 0..MAXIMUM_POSITION_MS || durationMs != null && (durationMs !in 0..MAXIMUM_POSITION_MS || positionMs > durationMs)) {
            throw WatchFailure("invalidLocalState")
        }
        val selected = mediaId ?: throw WatchFailure("invalidState")
        this.positionMs = positionMs; this.paused = paused
        localState = localState.copy(resumePositions = (localState.resumePositions.filterNot { it.mediaId == selected } + ResumePosition(selected, positionMs)).takeLast(256))
    }
    fun returnToLibrary() { playerPresented = false }
    fun continueWatching() {
        if (phase !in setOf(WatchPhase.active, WatchPhase.preparing)) throw WatchFailure("invalidState")
        playerPresented = true
    }
    fun cancel(owner: PlaybackScope): List<WatchEffect> { check(owner, WatchPhase.preparing); return end() }
    fun end(): List<WatchEffect> {
        if (phase !in setOf(WatchPhase.active, WatchPhase.preparing)) return emptyList()
        val next = scope.replacingMedia(); val effects = releaseEffects()
        scope = next; phase = WatchPhase.ended; paused = true; playerPresented = false
        return effects
    }
    fun setPreferences(preferences: LocalPreferences) { preferences.validate(); localState = localState.copy(preferences = preferences) }
    private fun releaseEffects(): List<WatchEffect> = if (phase in setOf(WatchPhase.active, WatchPhase.preparing)) listOf(WatchEffect.Release(scope)) else emptyList()
    private fun check(owner: PlaybackScope, expected: WatchPhase) {
        scope.check(owner); if (phase != expected) throw WatchFailure("invalidState")
    }
    companion object { const val MAXIMUM_POSITION_MS = 604_800_000L }
}
