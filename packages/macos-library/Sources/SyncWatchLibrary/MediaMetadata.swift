import Foundation

/// Local observed media facts. These values never authorize a shared edition or expose a path to peers.
public struct MediaMetadata: Equatable, Sendable {
    public let durationMs: Int64?
    public let width: Int
    public let height: Int
    public let audioTracks: Int
    public let subtitleTracks: Int

    public init(durationMs: Int64?, width: Int, height: Int, audioTracks: Int, subtitleTracks: Int) throws {
        guard durationMs.map({ $0 >= 0 }) ?? true, width >= 0, height >= 0,
            audioTracks >= 0, subtitleTracks >= 0
        else { throw MediaMetadataFailure.unavailable }
        self.durationMs = durationMs
        self.width = width
        self.height = height
        self.audioTracks = audioTracks
        self.subtitleTracks = subtitleTracks
    }
}

public enum MediaMetadataFailure: Error, Sendable { case unavailable, changed }

public protocol MediaMetadataReading: Sendable {
    func read(_ file: LocalMediaFile) async throws -> MediaMetadata
    func close() async
}
