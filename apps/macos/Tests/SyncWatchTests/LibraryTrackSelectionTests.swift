import SyncWatchDesign
import SyncWatchDomain
import SyncWatchLibrary
import Testing

@testable import SyncWatch

@Test func libraryTrackDraftRejectsStaleMenusAndResolvesFreshNativeIds() throws {
    let metadata = try MediaMetadata(durationMs: 1000, width: 1, height: 1, audioTracks: 2, subtitleTracks: 2,
        audioTrackNames: ["First", "Second"], subtitleTrackNames: ["English", "Русский"])
    var model = LibraryTrackSelection()
    model.reset(metadata)
    #expect(model.audioName == "First" && model.subtitlesDisabled && model.subtitleName == nil)
    model.open("audio", language: "en")
    let audio = try #require(model.menu)
    var request: SelectionMenuRequest?
    audio.dispatch("1", contextToken: audio.contextToken) { request = $0 }
    let old = try #require(request)
    model.select(old)
    let captured = model.preferences
    #expect(model.audioName == "Second" && model.menu == nil)
    let native = [PlaybackTrack(id: -1, name: "Disable"), .init(id: 101, name: "First"), .init(id: 299, name: "Second")]
    #expect(try captured.resolve(native, subtitles: false) == 299)
    #expect(throws: MediaMetadataFailure.self) { try captured.resolve(native.reversed(), subtitles: false) }
    #expect(throws: MediaMetadataFailure.self) { try captured.resolve([.init(id: 1, name: "Other")], subtitles: false) }
    model.open("subtitles", language: "ru")
    let subtitles = try #require(model.menu)
    model.select(old)
    #expect(model.menu?.contextToken == subtitles.contextToken && model.subtitlesDisabled)
    subtitles.dispatch("1", contextToken: subtitles.contextToken) { model.select($0) }
    #expect(model.subtitleName == "Русский" && !model.subtitlesDisabled)
    #expect(captured.subtitleIndex == nil) // A pending Start owns an immutable draft.
    model.reset(metadata)
    model.select(old)
    #expect(model.audioName == "First" && model.subtitlesDisabled && model.menu == nil)
    model.reset()
    model.open("audio", language: "en")
    #expect(model.menu == nil && model.audioName == nil && !model.subtitlesDisabled)
}
