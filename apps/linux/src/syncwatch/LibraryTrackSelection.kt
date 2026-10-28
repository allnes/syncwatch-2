package syncwatch

import syncwatch.design.*
import syncwatch.domain.PlaybackTrack
import syncwatch.library.MediaMetadata

/** Names/ordinals cross native input ownership; inspector IDs never do. */
internal data class LocalTrackPreferences(val audioNames: List<String>? = null,
    val subtitleNames: List<String>? = null, val audioIndex: Int? = null, val subtitleIndex: Int? = null) {
    fun resolve(tracks: List<PlaybackTrack>, subtitles: Boolean): Int? {
        val expected = (if (subtitles) subtitleNames else audioNames) ?: return null
        val actual = tracks.filter { it.id >= 0 }
        check(actual.map { it.name } == expected) { "media-tracks-changed" }
        val index = (if (subtitles) subtitleIndex else audioIndex) ?: return if (subtitles) -1 else null
        return actual.getOrNull(index)?.id ?: error("media-tracks-changed")
    }
}

/** One local metadata generation; no room or live-player authority. */
@ConsistentCopyVisibility
internal data class LibraryTrackSelection private constructor(
    private val sourceId: String, private val revision: Long,
    val preferences: LocalTrackPreferences, val menu: SelectionMenuPresentation?) {
    constructor() : this("library-tracks-${java.util.UUID.randomUUID()}", 0, LocalTrackPreferences(), null)
    fun reset(metadata: MediaMetadata? = null) = dismiss().copy(preferences = LocalTrackPreferences(
        metadata?.audioTrackNames, metadata?.subtitleTrackNames,
        if (metadata?.audioTrackNames?.isNotEmpty() == true) 0 else null))
    val audioName get() = preferences.audioIndex?.let { preferences.audioNames!![it] }
    val subtitleName get() = preferences.subtitleIndex?.let { preferences.subtitleNames!![it] }
    val subtitlesDisabled get() = preferences.subtitleNames != null && preferences.subtitleIndex == null
    fun open(kind: String, language: String): LibraryTrackSelection {
        val next = dismiss()
        if (kind !in setOf("audio", "subtitles")) return next
        val names = (if (kind == "audio") preferences.audioNames else preferences.subtitleNames) ?: return next
        if (names.isEmpty()) return next
        val entries = names.mapIndexed { index, name -> SelectionMenuEntry(index.toString(),
            name.ifEmpty { SyncWatchCopy.text("unknown", language) }) }.toMutableList()
        if (kind == "subtitles") entries.add(0, SelectionMenuEntry.offTrack)
        val selected = (if (kind == "audio") preferences.audioIndex else preferences.subtitleIndex)?.toString()
            ?: if (kind == "subtitles") "-1" else null
        return next.copy(menu = SelectionMenuPresentation(kind, sourceId, next.revision, entries, selected, true))
    }
    fun select(request: SelectionMenuRequest): LibraryTrackSelection {
        val current = menu ?: return this
        if (!current.allows(request.entryID) || request.sourceID != sourceId || request.revision != revision ||
            request.kind != current.kind || request.scope != "local" || request.action != current.definition?.action) return this
        val index = request.entryID.toIntOrNull() ?: return this
        return dismiss().copy(preferences = if (request.kind == "audio") preferences.copy(audioIndex = index)
            else preferences.copy(subtitleIndex = index.takeIf { it >= 0 }))
    }
    fun dismiss() = copy(revision = revision + 1, menu = null)
}
