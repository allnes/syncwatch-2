package syncwatch

import syncwatch.design.*
import syncwatch.domain.PlaybackTrack
import syncwatch.library.MediaMetadata

internal fun libraryTrackSelectionChecks() {
    val metadata = MediaMetadata(1_000, 1, 1, 2, 2, listOf("First", "Second"), listOf("English", "Русский"))
    var model = LibraryTrackSelection().reset(metadata)
    check(model.audioName == "First" && model.subtitlesDisabled && model.subtitleName == null)
    model = model.open("audio", "en")
    val audio = checkNotNull(model.menu); var request: SelectionMenuRequest? = null
    audio.dispatch("1", audio.contextToken) { request = it }
    val old = checkNotNull(request); model = model.select(old)
    val captured = model.preferences
    check(model.audioName == "Second" && model.menu == null)
    val native = listOf(PlaybackTrack(-1, "Disable"), PlaybackTrack(101, "First"), PlaybackTrack(299, "Second"))
    check(captured.resolve(native, false) == 299)
    check(runCatching { captured.resolve(native.reversed(), false) }.isFailure)
    check(runCatching { captured.resolve(listOf(PlaybackTrack(1, "Other")), false) }.isFailure)
    model = model.open("subtitles", "ru"); val subtitles = checkNotNull(model.menu)
    model = model.select(old)
    check(model.menu?.contextToken == subtitles.contextToken && model.subtitlesDisabled)
    subtitles.dispatch("1", subtitles.contextToken) { model = model.select(it) }
    check(model.subtitleName == "Русский" && !model.subtitlesDisabled && captured.subtitleIndex == null)
    model = model.reset(metadata).select(old)
    check(model.audioName == "First" && model.subtitlesDisabled && model.menu == null)
    model = model.reset().open("audio", "en")
    check(model.menu == null && model.audioName == null && !model.subtitlesDisabled)
    println("SYNCWATCH_LIBRARY_TRACK_DRAFT_OK fresh IDs, reordered/changed input, stale menu, immutable Start")
}
