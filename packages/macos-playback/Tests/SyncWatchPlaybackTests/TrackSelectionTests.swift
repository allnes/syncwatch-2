import Foundation
import SyncWatchDomain
import SyncWatchPlayback
import Testing

@Test(.enabled(if: ProcessInfo.processInfo.environment["SYNCWATCH_NATIVE_MEDIA_PACKAGE"] != nil))
func trackSelectionUsesNativeAcknowledgementAndOwnerScope() async throws {
    let environment = ProcessInfo.processInfo.environment
    let package = try #require(environment["SYNCWATCH_NATIVE_MEDIA_PACKAGE"])
    let file = try #require(environment["SYNCWATCH_NATIVE_MEDIA_FILE"])
    let player = VLCPlayback()
    let scope = try PlaybackScope(clientRunID: "swift-tracks", mediaGeneration: 1)
    func observeTrack(_ expected: Int32, subtitles: Bool = false) async throws {
        let deadline = ContinuousClock.now.advanced(by: .seconds(3))
        while try await player.selectedTrack(subtitles: subtitles, scope: scope) != expected {
            guard ContinuousClock.now < deadline else { throw PlaybackFailure.engine }
            try await Task.sleep(for: .milliseconds(20))
        }
    }
    do {
        try await player.open(package: URL(filePath: package))
        try await player.load(URL(filePath: file), scope: scope)
        let deadline = ContinuousClock.now.advanced(by: .seconds(5))
        while try await player.observe(scope).status != .ready {
            guard ContinuousClock.now < deadline else { throw PlaybackFailure.engine }
            try await Task.sleep(for: .milliseconds(20))
        }
        let tracks = try await player.tracks(subtitles: false, scope: scope)
        let first = try #require(tracks.first { $0.id >= 0 })
        try await observeTrack(first.id)
        try await player.selectTrack(-1, subtitles: false, scope: scope)
        try await observeTrack(-1)
        try await player.selectTrack(first.id, subtitles: false, scope: scope)
        try await observeTrack(first.id)
        try await observeTrack(-1, subtitles: true)
        await #expect(throws: PlaybackFailure.invalid) {
            try await player.selectTrack(Int32.max, subtitles: false, scope: scope)
        }
        let foreign = try PlaybackScope(clientRunID: "foreign-tracks", mediaGeneration: 1)
        await #expect(throws: ContractRejection.foreignRun) {
            try await player.selectedTrack(subtitles: false, scope: foreign)
        }
        let cancelled = Task {
            withUnsafeCurrentTask { $0?.cancel() }
            return try await player.selectedTrack(subtitles: false, scope: scope)
        }
        await #expect(throws: CancellationError.self) { try await cancelled.value }
        let next = try scope.replacingMedia()
        try await player.load(URL(filePath: file), scope: next)
        await #expect(throws: ContractRejection.staleGeneration) {
            try await player.selectedTrack(subtitles: false, scope: scope)
        }
        try await player.stop(next)
        await #expect(throws: PlaybackFailure.unavailable) {
            try await player.selectedTrack(subtitles: false, scope: next)
        }
    } catch {
        await player.close()
        throw error
    }
    await player.close()
    await player.close()
    await #expect(throws: PlaybackFailure.closed) { try await player.selectedTrack(subtitles: false, scope: scope) }
}
