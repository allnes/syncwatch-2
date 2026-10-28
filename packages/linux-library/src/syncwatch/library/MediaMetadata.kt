package syncwatch.library

/** Observed local facts. No peer path or shared-edition authority is derived from metadata. */
class MediaMetadata(val durationMs: Long?, val width: Int, val height: Int,
    val audioTracks: Int, val subtitleTracks: Int,
    audioTrackNames: List<String>? = null, subtitleTrackNames: List<String>? = null) {
    val audioTrackNames: List<String>? = names(audioTrackNames, audioTracks)
    val subtitleTrackNames: List<String>? = names(subtitleTrackNames, subtitleTracks)
    init {
        require(durationMs == null || durationMs >= 0)
        require(width >= 0 && height >= 0 && audioTracks >= 0 && subtitleTracks >= 0)
    }
    override fun equals(other: Any?): Boolean = other is MediaMetadata &&
        durationMs == other.durationMs && width == other.width && height == other.height &&
        audioTracks == other.audioTracks && subtitleTracks == other.subtitleTracks &&
        audioTrackNames == other.audioTrackNames && subtitleTrackNames == other.subtitleTrackNames
    override fun hashCode(): Int = listOf(durationMs, width, height, audioTracks, subtitleTracks,
        audioTrackNames, subtitleTrackNames).hashCode()
    private companion object {
        fun names(value: List<String>?, count: Int): List<String>? {
            if (value == null) return null
            val copy = value.toList()
            require(copy.size == count && copy.all { '\u0000' !in it && it.toByteArray(Charsets.UTF_8).size <= 4096 })
            return java.util.Collections.unmodifiableList(copy)
        }
    }
}

interface MediaMetadataReader {
    suspend fun read(file: LocalMediaFile): MediaMetadata
    suspend fun close()
}
