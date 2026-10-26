import Foundation
import SyncWatchDomain
import SyncWatchLibrary
import Testing

@testable import SyncWatch

private actor WaitingMediaPlayer: PlaybackPort {
    var entered = false
    var stopped = false
    func observe(_ scope: PlaybackScope) async throws -> PlaybackObservation {
        entered = true
        defer { stopped = true }
        try await Task.sleep(for: .seconds(30))
        throw ContractRejection.malformed
    }
    func load(_ localFile: URL, scope: PlaybackScope) async throws { throw ContractRejection.malformed }
    func setPaused(_ paused: Bool, scope: PlaybackScope) async throws { throw ContractRejection.malformed }
    func seek(to positionMs: Int64, scope: PlaybackScope) async throws { throw ContractRejection.malformed }
    func setRate(_ rate: Double, scope: PlaybackScope) async throws { throw ContractRejection.malformed }
    func setVolume(_ volume: Double, muted: Bool, scope: PlaybackScope) async throws {
        throw ContractRejection.malformed
    }
    func tracks(subtitles: Bool, scope: PlaybackScope) async throws -> [PlaybackTrack] {
        throw ContractRejection.malformed
    }
    func selectTrack(_ id: Int32, subtitles: Bool, scope: PlaybackScope) async throws {
        throw ContractRejection.malformed
    }
    func stop(_ scope: PlaybackScope) async throws { throw ContractRejection.malformed }
    func close() async {}
}

@Test @MainActor func sharedMediaPreparationCancelsBeforeOwnerClose() async throws {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    try Data("owned fixture".utf8).write(to: root.appendingPathComponent("owned.avi"))
    let access = try LibraryFolderAccess.selected(root)
    let media = try #require(await FileSystemLibrary().scan(root: root, rootID: access.rootId, recursive: false).first)
    let selection = LibraryMediaSelection(media: media, access: access)
    for closeOwner in [false, true] {
        let preparation = SharedMediaPreparation()
        let player = WaitingMediaPlayer()
        let worker = Task { try await preparation.prepare(selection, player: player, scope: .fresh()) }
        for _ in 0..<1_000 {
            if await player.entered { break }
            try await Task.sleep(for: .milliseconds(1))
        }
        #expect(await player.entered)
        if closeOwner { await preparation.close() } else { worker.cancel() }
        for _ in 0..<1_000 {
            if await player.stopped { break }
            try await Task.sleep(for: .milliseconds(1))
        }
        let stoppedBeforeCleanup = await player.stopped
        await preparation.close()
        await preparation.close()
        #expect(stoppedBeforeCleanup)
        do {
            _ = try await worker.value
            Issue.record("Canceled preparation succeeded")
        } catch is CancellationError {}
    }
}
