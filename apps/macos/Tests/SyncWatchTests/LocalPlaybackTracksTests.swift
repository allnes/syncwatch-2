import Foundation
import SyncWatchDesign
import SyncWatchDomain
import Testing

@testable import SyncWatch

private actor TrackPlayer: PlaybackTrackControlPort {
    enum Failure: Error { case rejected }
    var selected: Int32 = 1
    var reject = false
    var hold = false
    var waiting: CheckedContinuation<Void, Never>?
    private(set) var selections = 0
    private(set) var reads = 0
    private(set) var lastScope: PlaybackScope?
    func configure(selected: Int32? = nil, reject: Bool = false, hold: Bool = false) {
        if let selected { self.selected = selected }
        self.reject = reject
        self.hold = hold
    }
    func release() {
        waiting?.resume()
        waiting = nil
    }
    func tracks(subtitles: Bool, scope: PlaybackScope) async -> [PlaybackTrack] {
        reads += 1
        lastScope = scope
        if hold { await withCheckedContinuation { waiting = $0 } }  // Intentionally ignores cancellation.
        return [.init(id: -1, name: "Disable"), .init(id: 1, name: "First"), .init(id: 2, name: "Second")]
    }
    func selectedTrack(subtitles: Bool, scope: PlaybackScope) -> Int32 { selected }
    func selectTrack(_ id: Int32, subtitles: Bool, scope: PlaybackScope) throws {
        selections += 1
        if reject { throw Failure.rejected }
    }
    func load(_ localFile: URL, scope: PlaybackScope) {}
    func observe(_ scope: PlaybackScope) throws -> PlaybackObservation { throw Failure.rejected }
    func setPaused(_ paused: Bool, scope: PlaybackScope) {}
    func seek(to positionMs: Int64, scope: PlaybackScope) {}
    func setRate(_ rate: Double, scope: PlaybackScope) {}
    func setVolume(_ volume: Double, muted: Bool, scope: PlaybackScope) {}
    func stop(_ scope: PlaybackScope) {}
    func close() {}
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
