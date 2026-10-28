package syncwatch

import java.nio.file.Path
import java.nio.file.Files
import syncwatch.library.LocalFileAccess
import kotlin.coroutines.Continuation
import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine
import kotlinx.coroutines.async
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import syncwatch.design.*
import syncwatch.domain.*

private class TrackPlayer : PlaybackExternalTrackPort {
    var selected = 1
    var autoAcknowledge = false
    var reject = false
    var hold = false
    var waiting: Continuation<Unit>? = null
    var selections = 0
    var reads = 0
    var lastScope: PlaybackScope? = null
    var attachments = 0
    private var attached = false
    fun release() { val next = waiting; waiting = null; next?.resume(Unit) }
    override suspend fun tracks(subtitles: Boolean, scope: PlaybackScope): List<PlaybackTrack> {
        reads++; lastScope = scope
        if (hold) suspendCoroutine<Unit> { waiting = it } // Deliberately ignore cancellation.
        val entries = listOf(PlaybackTrack(-1, "Disable"), PlaybackTrack(1, "First"), PlaybackTrack(2, "Second"))
        return if (attached) entries + PlaybackTrack(3, "External") else entries
    }
    override suspend fun selectedTrack(subtitles: Boolean, scope: PlaybackScope) = selected
    override suspend fun selectTrack(id: Int, subtitles: Boolean, scope: PlaybackScope) { selections++; check(!reject); if (autoAcknowledge) selected = id }
    override suspend fun load(localFile: Path, scope: PlaybackScope) = error("unused")
    override suspend fun observe(scope: PlaybackScope): PlaybackObservation = error("unused")
    override suspend fun setPaused(paused: Boolean, scope: PlaybackScope) = error("unused")
    override suspend fun seek(positionMs: Long, scope: PlaybackScope) = error("unused")
    override suspend fun setRate(rate: Double, scope: PlaybackScope) = error("unused")
    override suspend fun setVolume(volume: Double, muted: Boolean, scope: PlaybackScope) = error("unused")
    override suspend fun stop(scope: PlaybackScope) = error("unused")
    override suspend fun close() = Unit
    override suspend fun attachTrack(localFile: Path, subtitles: Boolean, scope: PlaybackScope) {
        attachments++; lastScope = scope; check(!reject)
        attached = true; if (autoAcknowledge) selected = 3
    }
}

private class TrackFilePicker : ExternalTrackChoosing {
    var file: LocalFileAccess? = null
    var hold = false
    var calls = 0
    var waiting: Continuation<LocalFileAccess?>? = null
    override suspend fun choose(kind: String, language: String): LocalFileAccess? {
        calls++
        return if (hold) suspendCoroutine { waiting = it } else file
    }
    override fun cancel() = Unit // Deliberately late to exercise the coordinator's join/identity guard.
    fun release() { val next = waiting; waiting = null; next?.resume(file) }
}

private suspend fun externalTrackFileChecks(owner: CoroutineScope) {
    val directory = Files.createTempDirectory("syncwatch-external-")
    val file = directory.resolve("Audio Кино 映画.wav")
    Files.writeString(file, "owned choice fixture")
    val player = TrackPlayer(); val picker = TrackFilePicker()
    val model = LocalPlaybackTracks(player, PlaybackScope.fresh().replacingMedia(), owner, picker)
    suspend fun until(condition: () -> Boolean) = withTimeout(2_000) { while (!condition()) delay(5) }
    fun choose(): SelectionMenuRequest {
        val menu = checkNotNull(model.menu); var request: SelectionMenuRequest? = null
        menu.dispatch(SyncWatchSelectionMenu.externalFileID, menu.contextToken) { request = it }
        return checkNotNull(request)
    }
    try {
        model.open("audio", "ru"); model.settled()
        check(model.menu?.entries?.last()?.label == SyncWatchCopy.text("openAudioTrack", "ru"))
        model.select(choose()); model.settled(); check(player.attachments == 0 && player.selected == 1)
        picker.file = LocalFileAccess.selected(file)
        val old = choose(); model.select(old); until { player.attachments == 1 }
        check(model.menu == null); model.dismissMenu(); check(player.selected == 1)
        player.selected = 3; model.settled()
        model.open("audio"); model.settled()
        check(model.menu?.selectedID == "3" && model.menu?.entries?.first { it.id == "3" }?.label == file.fileName.toString())
        model.select(old); check(player.attachments == 1)
        player.reject = true; model.select(choose()); model.settled()
        check(model.menu?.isValid == true && model.menu?.entries?.any { it.id == SyncWatchSelectionMenu.externalFileErrorID && !it.enabled } == true)
        player.reject = false; picker.hold = true; model.select(choose()); until { picker.waiting != null }
        model.dismissMenu(); check(model.menu == null && picker.waiting != null)
        val before = player.attachments
        val closing = owner.async { model.close() }
        until { model.menu == null }; check(!closing.isCompleted)
        picker.release(); closing.await()
        check(player.attachments == before && model.menu == null)
        model.releaseExternalAccess()
    } finally {
        picker.release(); model.close(); model.releaseExternalAccess()
        Files.deleteIfExists(file); Files.deleteIfExists(directory)
    }
}

internal suspend fun localPlaybackTracksChecks(owner: CoroutineScope) {
    companionPreselectionChecks(owner)
    val player = TrackPlayer(); val scope = PlaybackScope.fresh().replacingMedia()
    val model = LocalPlaybackTracks(player, scope, owner)
    suspend fun until(condition: () -> Boolean) = withTimeout(2_000) { while (!condition()) delay(5) }
    try {
        val invalid = LocalTrackPreferences(listOf("First", "Second"), listOf("Changed"), 1)
        check(runCatching { model.applyInitial(invalid) }.isFailure && player.selections == 0)
        val initialPreferences = LocalTrackPreferences(listOf("First", "Second"), listOf("First", "Second"), 1)
        val applying = owner.async { model.applyInitial(initialPreferences) }
        until { player.selections == 1 }; check(model.menu == null)
        player.autoAcknowledge = true; player.selected = 2; applying.await()
        check(player.selections == 2 && player.selected == -1)
        check(model.libraryPresentation(LibraryPresentation()).metadataSubtitlesDisabled)
        player.autoAcknowledge = false; player.selected = 1; player.selections = 0
        model.open("audio"); model.settled(); check(player.lastScope == scope)
        val initial = checkNotNull(model.menu); var request: SelectionMenuRequest? = null
        initial.dispatch("2", initial.contextToken) { request = it }
        model.select(checkNotNull(request)); until { player.selections == 1 }
        check(model.menu?.enabled == false && model.menu?.selectedID == "1")
        player.selected = 2; model.settled(); check(model.menu == null)
        model.open("audio"); model.settled(); check(model.menu?.enabled == true && model.menu?.selectedID == "2")
        check(model.libraryPresentation(LibraryPresentation(metadataAudioName = "obsolete draft")).metadataAudioName == "Second")
        model.select(checkNotNull(request)); check(player.selections == 1)
        player.reject = true
        val current = checkNotNull(model.menu); current.dispatch("1", current.contextToken, model::select)
        model.settled(); check(model.menu?.isValid == false)
        player.reject = false; model.open("subtitles"); model.settled()
        check(model.menu?.isValid == true && model.menu?.kind == "subtitles")
        player.hold = true; val before = player.reads
        model.open("audio"); until { player.reads == before + 1 }
        model.open("subtitles"); model.dismiss(); player.release(); model.settled(); check(model.menu == null)
        model.open("audio"); until { player.reads == before + 2 }
        val closing = owner.launch { model.close() }; delay(5); check(!closing.isCompleted)
        player.release(); closing.join(); check(model.menu == null)
        model.open("audio"); check(model.menu == null)
    } finally { player.release(); model.close() }
    externalTrackFileChecks(owner)
    println("SYNCWATCH_LOCAL_TRACKS_OK acknowledgement, stale input, late completion, retry, awaited close")
}

private suspend fun companionPreselectionChecks(owner: CoroutineScope) {
    val root = Files.createTempDirectory("syncwatch-companion-draft-")
    try {
        Files.createDirectories(root.resolve("subs"))
        for (name in listOf("Movie.mkv", "Movie.en.srt", "subs/Movie.en.srt", "Movie.wav")) Files.writeString(root.resolve(name), name)
        val movie = syncwatch.library.FileSystemLibrary(mapOf("srt" to syncwatch.library.LibraryCompanionKind.subtitles,
            "wav" to syncwatch.library.LibraryCompanionKind.audio)).scan(root, java.util.UUID.randomUUID().toString(), true).single()
        val metadata = syncwatch.library.MediaMetadata(1_000, 1, 1, 2, 2, listOf("First", "Second"), listOf("First", "Second"))
        var draft = LibraryTrackSelection().reset(metadata, movie.companions).open("subtitles", "en")
        val menu = checkNotNull(draft.menu)
        val entries = menu.entries.filter { it.id.startsWith("companion:") }
        check(entries.map { it.label } == listOf("Movie.en.srt", "subs/Movie.en.srt"))
        var chosen: SelectionMenuRequest? = null
        menu.dispatch(entries.last().id, menu.contextToken) { chosen = it; draft = draft.select(it) }
        val preferences = draft.preferences
        check(preferences.subtitleFile?.relativePath == "subs/Movie.en.srt" && !draft.subtitlesDisabled)
        draft = draft.reset(metadata).select(checkNotNull(chosen))
        check(draft.preferences.subtitleFile == null && draft.subtitlesDisabled)
        val scope = PlaybackScope.fresh().replacingMedia()
        val player = TrackPlayer().apply { autoAcknowledge = true }
        val playback = LocalPlaybackTracks(player, scope, owner)
        try {
            playback.applyInitial(preferences)
            check(player.attachments == 1 && player.selected == 3)
            val live = playback.libraryPresentation(LibraryPresentation(metadataSubtitlesDisabled = true, metadataSubtitleName = "obsolete draft"))
            check(live.metadataSubtitleName == "Movie.en.srt" && !live.metadataSubtitlesDisabled)
            playback.open("subtitles"); playback.settled()
            check(playback.menu?.selectedID == "3" && playback.menu?.entries?.last()?.label == "Movie.en.srt")
        } finally { playback.close(); playback.releaseExternalAccess() }
        val audio = movie.companions.first { it.kind == syncwatch.library.LibraryCompanionKind.audio }
        Files.delete(audio.file)
        val rejected = TrackPlayer(); val other = LocalPlaybackTracks(rejected, scope, owner)
        try {
            check(runCatching { other.applyInitial(preferences.copy(audioFile = audio)) }.isFailure)
            check(rejected.attachments == 0 && rejected.selections == 0)
        } finally { other.close(); other.releaseExternalAccess() }
    } finally { root.toFile().deleteRecursively(); check(!Files.exists(root)) }
}
