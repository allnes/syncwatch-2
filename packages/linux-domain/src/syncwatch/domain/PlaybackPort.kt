package syncwatch.domain

import java.nio.file.Path

enum class PlaybackStatus { unloaded, loading, ready, failed }

data class PlaybackObservation(
    val scope: PlaybackScope,
    val sequence: ULong,
    val status: PlaybackStatus,
    val positionMs: Long,
    val durationMs: Long?,
    val paused: Boolean,
    val rate: Double,
    val seekable: Boolean,
    val buffering: Boolean,
    val ended: Boolean,
    val width: Int,
    val height: Int,
    val videoOutputs: Int,
    val volume: Double?,
    val muted: Boolean,
) {
    init {
        if (positionMs !in 0..WatchSession.MAXIMUM_POSITION_MS
            || durationMs != null && (durationMs !in 0..WatchSession.MAXIMUM_POSITION_MS || positionMs > durationMs)
            || !rate.isFinite() || rate !in 0.25..4.0 || width < 0 || height < 0 || videoOutputs < 0
            || volume != null && (!volume.isFinite() || volume !in 0.0..1.0)
            || status != PlaybackStatus.ready && (!paused || seekable || rate != 1.0)
            || status == PlaybackStatus.unloaded && (positionMs != 0L || durationMs != null)) throw WatchFailure("malformed")
    }
}

data class PlaybackTrack(val id: Int, val name: String)

/** Local submissions only. Actual engine observations acknowledge playback state. */
interface PlaybackPort {
    suspend fun load(localFile: Path, scope: PlaybackScope)
    suspend fun observe(scope: PlaybackScope): PlaybackObservation
    suspend fun setPaused(paused: Boolean, scope: PlaybackScope)
    suspend fun seek(positionMs: Long, scope: PlaybackScope)
    suspend fun setRate(rate: Double, scope: PlaybackScope)
    suspend fun setVolume(volume: Double, muted: Boolean, scope: PlaybackScope)
    suspend fun tracks(subtitles: Boolean, scope: PlaybackScope): List<PlaybackTrack>
    suspend fun selectTrack(id: Int, subtitles: Boolean, scope: PlaybackScope)
    suspend fun stop(scope: PlaybackScope)
    suspend fun close()
}

/** Observed local track selection; -1 means disabled/no active track. */
interface PlaybackTrackControlPort : PlaybackPort {
    suspend fun selectedTrack(subtitles: Boolean, scope: PlaybackScope): Int
}

/** Local file attachment submission; selected-ID acknowledgement is separate. */
interface PlaybackExternalTrackPort : PlaybackTrackControlPort {
    suspend fun attachTrack(localFile: Path, subtitles: Boolean, scope: PlaybackScope)
}
