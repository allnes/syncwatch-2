package syncwatch.library

/** Observed local facts. No peer path or shared-edition authority is derived from metadata. */
data class MediaMetadata(val durationMs: Long?, val width: Int, val height: Int,
    val audioTracks: Int, val subtitleTracks: Int) {
    init {
        require(durationMs == null || durationMs >= 0)
        require(width >= 0 && height >= 0 && audioTracks >= 0 && subtitleTracks >= 0)
    }
}

interface MediaMetadataReader {
    suspend fun read(file: LocalMediaFile): MediaMetadata
    suspend fun close()
}
