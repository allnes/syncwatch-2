import CryptoKit
import Foundation
import SyncWatchDomain
import SyncWatchPlayback
import Testing

@Test(.enabled(if: ProcessInfo.processInfo.environment["SYNCWATCH_NATIVE_MEDIA_PACKAGE"] != nil))
func loadedContentUsesTheNativePlayerOwner() async throws {
    let environment = ProcessInfo.processInfo.environment
    let package = try #require(environment["SYNCWATCH_NATIVE_MEDIA_PACKAGE"])
    let file = try #require(environment["SYNCWATCH_NATIVE_MEDIA_FILE"])
    let player = VLCPlayback()
    let scope = try PlaybackScope(clientRunID: "swift-loaded-content", mediaGeneration: 1)
    do {
        try await player.open(package: URL(filePath: package))
        try await player.load(URL(filePath: file), scope: scope)
        let before = try await player.contentVersion(scope)
        let expected = try Data(contentsOf: URL(filePath: file))
        #expect(before.sizeBytes == expected.count)
        #expect(before.description == "LoadedMediaVersion(redacted)")
        var digest = SHA256()
        var offset: Int64 = 0
        while offset < before.sizeBytes {
            let chunk = try await player.readContent(at: offset, capacity: 262_144, scope: scope)
            #expect(!chunk.isEmpty)
            guard !chunk.isEmpty else { throw PlaybackFailure.engine }
            digest.update(data: chunk)
            offset += Int64(chunk.count)
        }
        #expect(Array(digest.finalize()) == Array(SHA256.hash(data: expected)))
        #expect(try await player.contentVersion(scope) == before)
        #expect(try await player.readContent(at: offset, capacity: 8, scope: scope).isEmpty)
        await #expect(throws: PlaybackFailure.invalid) {
            try await player.readContent(at: 0, capacity: 262_145, scope: scope)
        }
        let next = try scope.replacingMedia()
        try await player.load(URL(filePath: file), scope: next)
        await #expect(throws: ContractRejection.staleGeneration) {
            try await player.contentVersion(scope)
        }
        await #expect(throws: ContractRejection.staleGeneration) {
            try await player.readContent(at: 0, capacity: 8, scope: scope)
        }
        #expect(try await player.contentVersion(next) != before)
        try await player.stop(next)
        await #expect(throws: PlaybackFailure.unavailable) {
            try await player.readContent(at: 0, capacity: 8, scope: next)
        }
    } catch {
        await player.close()
        throw error
    }
    await player.close()
    await #expect(throws: PlaybackFailure.closed) { try await player.contentVersion(scope) }
}
