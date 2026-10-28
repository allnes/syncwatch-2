import Foundation
import SyncWatchDesign
import SyncWatchDomain
import SyncWatchLibrary
import Testing

@testable import SyncWatch

@MainActor @Test func libraryCompanionsKeepDistinctFilesAndApplyBeforeAdmission() async throws {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: root.appendingPathComponent("subs"), withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    for name in ["Movie.mkv", "Movie.en.srt", "subs/Movie.en.srt", "Movie.wav"] {
        try Data(name.utf8).write(to: root.appendingPathComponent(name))
    }
    let files = try await FileSystemLibrary(companionExtensions: ["srt": .subtitles, "wav": .audio])
        .scan(root: root, rootID: UUID().uuidString.lowercased(), recursive: true)
    let movie = try #require(files.first)
    let metadata = try MediaMetadata(
        durationMs: 1000, width: 1, height: 1, audioTracks: 2, subtitleTracks: 2,
        audioTrackNames: ["First", "Second"], subtitleTrackNames: ["First", "Second"])
    var draft = LibraryTrackSelection()
    draft.reset(metadata, companions: movie.companions)
    draft.open("subtitles", language: "en")
    let menu = try #require(draft.menu)
    let entries = menu.entries.filter { $0.id.hasPrefix("companion:") }
    #expect(entries.map(\.label) == ["Movie.en.srt", "subs/Movie.en.srt"])
    var chosen: SelectionMenuRequest?
    menu.dispatch(try #require(entries.last).id, contextToken: menu.contextToken) {
        chosen = $0
        draft.select($0)
    }
    let preferences = draft.preferences
    #expect(preferences.subtitleFile?.relativePath == "subs/Movie.en.srt" && !draft.subtitlesDisabled)
    draft.reset(metadata)
    draft.select(try #require(chosen))
    #expect(draft.preferences.subtitleFile == nil && draft.subtitlesDisabled)
    let scope = try PlaybackScope.fresh().replacingMedia()
    let player = TrackPlayer()
    await player.acknowledgeAutomatically()
    let playback = LocalPlaybackTracks(player: player, scope: { scope })
    do {
        try await playback.applyInitial(preferences)
        #expect(await player.attachments == 1)
        #expect(await player.selected == 3)
        playback.open("subtitles")
        await playback.settled()
        #expect(playback.menu?.selectedID == "3" && playback.menu?.entries.last?.label == "Movie.en.srt")
    } catch {
        await playback.close()
        playback.releaseExternalAccess()
        throw error
    }
    await playback.close()
    playback.releaseExternalAccess()
    var invalid = preferences
    let audio = try #require(movie.companions.first { $0.kind == .audio })
    try FileManager.default.removeItem(at: audio.file)
    invalid.audioFile = audio
    let rejected = TrackPlayer()
    let other = LocalPlaybackTracks(player: rejected, scope: { scope })
    do {
        try await other.applyInitial(invalid)
        Issue.record("Missing companion admitted")
    } catch {}
    #expect(await rejected.attachments == 0)
    #expect(await rejected.selections == 0)
    await other.close()
    other.releaseExternalAccess()
}

private actor TrackPlayer: PlaybackExternalTrackPort {
    enum Failure: Error { case rejected }
    var selected: Int32 = 1
    var autoAcknowledge = false
    var reject = false
    var hold = false
    var waiting: CheckedContinuation<Void, Never>?
    private(set) var selections = 0
    private(set) var reads = 0
    private(set) var lastScope: PlaybackScope?
    private(set) var attachments = 0
    private var attached = false
    func configure(selected: Int32? = nil, reject: Bool = false, hold: Bool = false) {
        if let selected { self.selected = selected }
        self.reject = reject
        self.hold = hold
    }
    func acknowledgeAutomatically() { autoAcknowledge = true }
    func release() {
        waiting?.resume()
        waiting = nil
    }
    func tracks(subtitles: Bool, scope: PlaybackScope) async -> [PlaybackTrack] {
        reads += 1
        lastScope = scope
        if hold { await withCheckedContinuation { waiting = $0 } }  // Intentionally ignores cancellation.
        let base: [PlaybackTrack] = [
            .init(id: -1, name: "Disable"), .init(id: 1, name: "First"), .init(id: 2, name: "Second"),
        ]
        return attached ? base + [.init(id: 3, name: "External")] : base
    }
    func selectedTrack(subtitles: Bool, scope: PlaybackScope) -> Int32 { selected }
    func selectTrack(_ id: Int32, subtitles: Bool, scope: PlaybackScope) throws {
        selections += 1
        if reject { throw Failure.rejected }
        if autoAcknowledge { selected = id }
    }
    func load(_ localFile: URL, scope: PlaybackScope) {}
    func observe(_ scope: PlaybackScope) throws -> PlaybackObservation { throw Failure.rejected }
    func setPaused(_ paused: Bool, scope: PlaybackScope) {}
    func seek(to positionMs: Int64, scope: PlaybackScope) {}
    func setRate(_ rate: Double, scope: PlaybackScope) {}
    func setVolume(_ volume: Double, muted: Bool, scope: PlaybackScope) {}
    func stop(_ scope: PlaybackScope) {}
    func close() {}
    func attachTrack(_ localFile: URL, subtitles: Bool, scope: PlaybackScope) throws {
        attachments += 1
        lastScope = scope
        if reject { throw Failure.rejected }
        attached = true
        if autoAcknowledge { selected = 3 }
    }
}

@MainActor private final class TrackFilePicker: ExternalTrackChoosing {
    var file: LocalFileAccess?
    var hold = false
    var calls = 0
    var cancellations = 0
    var waiting: CheckedContinuation<LocalFileAccess?, Never>?
    func choose(kind: String, language: String) async -> LocalFileAccess? {
        calls += 1
        if hold { return await withCheckedContinuation { waiting = $0 } }
        return file
    }
    func cancel() { cancellations += 1 }
    func release() {
        let next = waiting
        waiting = nil
        next?.resume(returning: file)
    }
}

@MainActor @Test func externalTrackChoicesRemainScopedAwaitObservedIdsAndCloseLatePickers() async throws {
    let path = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: path, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: path) }
    let file = path.appendingPathComponent("Audio Кино 映画.wav")
    try Data("owned native-choice fixture".utf8).write(to: file)
    let player = TrackPlayer()
    let picker = TrackFilePicker()
    let scope = try PlaybackScope.fresh().replacingMedia()
    let model = LocalPlaybackTracks(player: player, scope: { scope }, picker: picker)
    func until(_ condition: () async -> Bool) async throws {
        let deadline = ContinuousClock.now.advanced(by: .seconds(2))
        while await !condition() {
            guard ContinuousClock.now < deadline else { throw TrackPlayer.Failure.rejected }
            try await Task.sleep(for: .milliseconds(5))
        }
    }
    func choose() throws -> SelectionMenuRequest {
        let menu = try #require(model.menu)
        var request: SelectionMenuRequest?
        menu.dispatch(SyncWatchSelectionMenu.externalFileID, contextToken: menu.contextToken) { request = $0 }
        return try #require(request)
    }
    do {
        model.open("audio", language: "ru")
        await model.settled()
        #expect(model.menu?.entries.last?.label == SyncWatchCopy.text("openAudioTrack", language: "ru"))
        model.select(try choose())
        await model.settled()
        #expect(await player.attachments == 0)
        #expect(await player.selected == 1)
        picker.file = try LocalFileAccess.selected(file)
        let old = try choose()
        model.select(old)
        try await until { await player.attachments == 1 }
        #expect(model.menu == nil)
        model.dismissMenu()
        #expect(await player.selected == 1)
        await player.configure(selected: 3)
        await model.settled()
        model.open("audio")
        await model.settled()
        #expect(
            model.menu?.selectedID == "3"
                && model.menu?.entries.first(where: { $0.id == "3" })?.label == file.lastPathComponent)
        model.select(old)
        #expect(await player.attachments == 1)
        await player.configure(reject: true)
        model.select(try choose())
        await model.settled()
        #expect(
            model.menu?.entries.contains(where: { $0.id == SyncWatchSelectionMenu.externalFileErrorID && !$0.enabled })
                == true)
        #expect(model.menu?.isValid == true)
        await player.configure()
        picker.hold = true
        model.select(try choose())
        try await until { picker.waiting != nil }
        let menuCancels = picker.cancellations
        model.dismissMenu()
        #expect(picker.cancellations == menuCancels && model.menu == nil)
        let before = await player.attachments
        let cancels = picker.cancellations
        var closed = false
        let ending = Task {
            await model.close()
            closed = true
        }
        try await until { picker.cancellations > cancels }
        #expect(!closed)
        picker.release()
        await ending.value
        #expect(await player.attachments == before && model.menu == nil)
        model.releaseExternalAccess()
    } catch {
        picker.release()
        await model.close()
        model.releaseExternalAccess()
        throw error
    }
}

@MainActor private final class TrackScope { var value: PlaybackScope? = PlaybackScope.fresh() }

@MainActor @Test func localTracksRequireAcknowledgementRejectStaleInputAndAwaitClose() async throws {
    let player = TrackPlayer()
    let scope = TrackScope()
    let model = LocalPlaybackTracks(player: player, scope: { scope.value })
    func until(_ condition: () async -> Bool) async throws {
        let deadline = ContinuousClock.now.advanced(by: .seconds(2))
        while await !condition() {
            guard ContinuousClock.now < deadline else { throw TrackPlayer.Failure.rejected }
            try await Task.sleep(for: .milliseconds(5))
        }
    }
    do {
        scope.value = try #require(scope.value).replacingMedia()
        model.open("audio")
        await model.settled()
        #expect(await player.lastScope == scope.value)
        let initial = try #require(model.menu)
        var request: SelectionMenuRequest?
        initial.dispatch("2", contextToken: initial.contextToken) { request = $0 }
        let selection = try #require(request)
        model.select(selection)
        try await until { await player.selections == 1 }
        #expect(model.menu?.enabled == false && model.menu?.selectedID == "1")
        await player.configure(selected: 2)
        await model.settled()
        #expect(model.menu == nil)
        model.open("audio")
        await model.settled()
        #expect(model.menu?.selectedID == "2" && model.menu?.enabled == true)
        model.select(selection)
        #expect(await player.selections == 1)
        await player.configure(reject: true)
        let current = try #require(model.menu)
        current.dispatch("1", contextToken: current.contextToken) { model.select($0) }
        await model.settled()
        #expect(model.menu?.isValid == false)
        await player.configure()
        model.open("subtitles")
        await model.settled()
        #expect(model.menu?.isValid == true && model.menu?.kind == "subtitles")
        let savedScope = scope.value
        scope.value = nil
        let reads = await player.reads
        model.open("audio")
        await model.settled()
        #expect(model.menu?.isValid == false)
        #expect(await player.reads == reads)
        scope.value = savedScope
        await player.configure(hold: true)
        let before = await player.reads
        model.open("audio")
        try await until { await player.reads == before + 1 }
        model.open("subtitles")
        model.dismiss()
        await player.release()
        await model.settled()
        #expect(model.menu == nil)
        model.open("audio")
        try await until { await player.reads == before + 2 }
        var closed = false
        let closing = Task {
            await model.close()
            closed = true
        }
        await Task.yield()
        #expect(!closed)
        await player.release()
        await closing.value
        #expect(closed && model.menu == nil)
        model.open("audio")
        #expect(model.menu == nil)
    } catch {
        await player.release()
        await model.close()
        throw error
    }
}

@MainActor @Test func initialLocalTracksValidateBothListsBeforeCommandsAndAwaitAcknowledgement() async throws {
    let player = TrackPlayer()
    let scope = PlaybackScope.fresh()
    let model = LocalPlaybackTracks(player: player, scope: { scope })
    do {
        let invalid = LocalTrackPreferences(audioNames: ["First", "Second"], subtitleNames: ["Changed"], audioIndex: 1)
        await #expect(throws: (any Error).self) { try await model.applyInitial(invalid) }
        #expect(await player.selections == 0)
        let selected = LocalTrackPreferences(
            audioNames: ["First", "Second"], subtitleNames: ["First", "Second"], audioIndex: 1)
        let applying = Task { try await model.applyInitial(selected) }
        let deadline = ContinuousClock.now.advanced(by: .seconds(2))
        while await player.selections == 0, ContinuousClock.now < deadline {
            try await Task.sleep(for: .milliseconds(5))
        }
        #expect(await player.selections == 1 && model.menu == nil)
        await player.acknowledgeAutomatically()
        await player.configure(selected: 2)
        try await applying.value
        #expect(await player.selections == 2)
        #expect(await player.selected == -1)
        await model.close()
        await #expect(throws: (any Error).self) { try await model.applyInitial(selected) }
    } catch {
        await model.close()
        throw error
    }
}
