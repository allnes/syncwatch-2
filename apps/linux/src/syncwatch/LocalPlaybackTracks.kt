package syncwatch

import androidx.compose.runtime.*
import java.util.UUID
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import syncwatch.design.*
import syncwatch.domain.PlaybackScope
import syncwatch.domain.PlaybackTrackControlPort
import syncwatch.domain.PlaybackExternalTrackPort
import syncwatch.library.LocalFileAccess

/** Movie-local selection; room metadata and Syncplay retain their own authority. */
internal class LocalPlaybackTracks(private val player: PlaybackTrackControlPort,
    private val scope: PlaybackScope, private val work: CoroutineScope, private val picker: ExternalTrackChoosing? = null) {
    private val sourceId = "tracks-${UUID.randomUUID()}"
    private var revision = 0L
    private var closed = false
    private var request: Job? = null
    private val pending = mutableSetOf<Job>()
    private var language = "en"
    private val externalFiles = mutableListOf<LocalFileAccess>()
    private val aliases = mutableMapOf<Pair<String, Int>, String>()
    var menu by mutableStateOf<SelectionMenuPresentation?>(null)
        private set

    /** Before watch admission/controls; validate both lists before mutating either. */
    suspend fun applyInitial(preferences: LocalTrackPreferences) {
        check(!closed)
        val audio = preferences.audioNames?.let { preferences.resolve(player.tracks(false, scope), false) }
        val subtitles = preferences.subtitleNames?.let { preferences.resolve(player.tracks(true, scope), true) }
        for ((id, isSubtitle) in listOf(audio to false, subtitles to true)) {
            if (id == null) continue
            check(!closed)
            acknowledge(id, isSubtitle)
        }
    }
    private suspend fun acknowledge(id: Int, subtitles: Boolean) {
        if (player.selectedTrack(subtitles, scope) == id) return
        player.selectTrack(id, subtitles, scope)
        withTimeout(3_000) { while (player.selectedTrack(subtitles, scope) != id) { check(!closed); delay(20) } }
    }
    fun open(kind: String, language: String = "en") {
        if (closed || kind !in setOf("audio", "subtitles")) return
        dismiss(); this.language = language; val current = revision
        pending.removeAll { it.isCompleted }
        request = work.launch {
            try { publish(snapshot(kind, current), current) }
            catch (_: Exception) { unavailable(kind, current) }
        }
        request?.let { pending.add(it) }
    }
    fun select(value: SelectionMenuRequest) {
        val before = menu ?: return
        if (closed || !before.allows(value.entryID) || value.scope != "local" || value.kind != before.kind ||
            value.sourceID != sourceId || value.revision != revision || value.action != before.definition?.action) return
        val id = value.entryID.toIntOrNull()
        if (id == null && value.entryID != SyncWatchSelectionMenu.externalFileID) return
        request?.cancel(); revision++; val current = revision
        menu = before.copy(revision = current, enabled = false)
        pending.removeAll { it.isCompleted }
        request = work.launch {
            try {
                val subtitles = value.kind == "subtitles"
                if (value.entryID == SyncWatchSelectionMenu.externalFileID) {
                    val external = player as? PlaybackExternalTrackPort ?: error("external-unavailable")
                    val chooser = picker ?: error("external-unavailable")
                    val file = chooser.choose(value.kind, language)
                    currentCoroutineContext().ensureActive()
                    check(!closed && current == revision)
                    if (file == null) { publish(snapshot(value.kind, current), current); return@launch }
                    externalFiles.add(file)
                    val previous = player.tracks(subtitles, scope).map { it.id }.toSet()
                    external.attachTrack(file.file, subtitles, scope)
                    val selected = attachment(subtitles, previous)
                    aliases[value.kind to selected] = file.file.fileName.toString()
                } else acknowledge(requireNotNull(id), subtitles)
                publish(snapshot(value.kind, current), current)
                if (!closed && current == revision) dismiss()
            } catch (_: Exception) { unavailable(value.kind, current) }
        }
        request?.let { pending.add(it) }
    }
    private suspend fun attachment(subtitles: Boolean, previous: Set<Int>): Int = withTimeout(3_000) {
        while (true) {
            currentCoroutineContext().ensureActive(); check(!closed)
            val id = player.selectedTrack(subtitles, scope)
            if (id >= 0 && id !in previous && player.tracks(subtitles, scope).any { it.id == id }) return@withTimeout id
            delay(20)
        }
        @Suppress("UNREACHABLE_CODE") error("external-acknowledgement")
    }
    private suspend fun snapshot(kind: String, current: Long): SelectionMenuPresentation {
        val subtitles = kind == "subtitles"
        val tracks = player.tracks(subtitles, scope)
        val selected = player.selectedTrack(subtitles, scope)
        val entries = tracks.map { SelectionMenuEntry(it.id.toString(), SelectionMenuEntry.observedLabel(aliases[kind to it.id] ?: it.name, language), disabledTrack = it.id < 0) }.toMutableList()
        if (subtitles && tracks.none { it.id < 0 }) entries.add(0, SelectionMenuEntry.offTrack)
        if (picker != null && player is PlaybackExternalTrackPort && entries.size < SyncWatchSelectionMenu.maximumEntries)
            SelectionMenuEntry.externalFile(kind, language)?.let(entries::add)
        return SelectionMenuPresentation(kind, sourceId, current,
            entries, selected.toString().takeIf { id -> entries.any { it.id == id } }, true)
    }
    private suspend fun unavailable(kind: String, current: Long) {
        currentCoroutineContext().ensureActive()
        if (closed || current != revision) return
        if (picker == null || player !is PlaybackExternalTrackPort) {
            publish(SelectionMenuPresentation(kind = kind), current)
            return
        }
        var value = try { snapshot(kind, current) } catch (_: Exception) {
            currentCoroutineContext().ensureActive()
            SelectionMenuPresentation(kind = kind, sourceID = sourceId, revision = current)
        }
        val entries = value.entries.toMutableList()
        if (entries.isEmpty()) SelectionMenuEntry.externalFile(kind, language)?.let(entries::add)
        entries.add(0, SelectionMenuEntry.externalFileFailure(language))
        value = value.copy(entries = entries, enabled = true)
        publish(value, current)
    }
    private fun publish(value: SelectionMenuPresentation, current: Long) {
        if (!closed && current == revision) menu = value
    }
    fun dismiss() { revision++; request?.cancel(); picker?.cancel(); menu = null }
    suspend fun close() {
        closed = true; dismiss(); pending.forEach { it.cancel() }
        pending.forEach { it.join() }; pending.clear(); request = null
    }
    suspend fun settled() { request?.join() }
    /** Only after native close has joined its input borrowers. */
    fun releaseExternalAccess() { externalFiles.clear(); aliases.clear() }
}
