import Foundation

public enum PlaybackStatus: Int32, Sendable {
    case unloaded, loading, ready, failed
}

public struct PlaybackObservation: Equatable, Sendable {
    public let scope: PlaybackScope
    public let sequence: UInt64
    public let status: PlaybackStatus
    public let positionMs: Int64
    public let durationMs: Int64?
    public let paused: Bool
    public let rate: Double
    public let seekable: Bool
    public let buffering: Bool
    public let ended: Bool
    public let width: Int
    public let height: Int
    public let videoOutputs: Int
    public let volume: Double?
    public let muted: Bool

    public init(
        scope: PlaybackScope, sequence: UInt64, status: PlaybackStatus, positionMs: Int64,
        durationMs: Int64?, paused: Bool, rate: Double, seekable: Bool,
        buffering: Bool, ended: Bool, width: Int, height: Int, videoOutputs: Int,
        volume: Double?, muted: Bool
    ) throws {
        guard (0...WatchSession.maximumPositionMs).contains(positionMs),
            durationMs.map({ (0...WatchSession.maximumPositionMs).contains($0) && positionMs <= $0 }) ?? true,
            rate.isFinite, (0.25...4).contains(rate), width >= 0, height >= 0, videoOutputs >= 0,
            volume.map({ $0.isFinite && (0...1).contains($0) }) ?? true,
            status == .ready || (paused && !seekable && rate == 1),
            status != .unloaded || (positionMs == 0 && durationMs == nil)
        else { throw ContractRejection.malformed }
        self.scope = scope
        self.sequence = sequence
        self.status = status
        self.positionMs = positionMs
        self.durationMs = durationMs
        self.paused = paused
        self.rate = rate
        self.seekable = seekable
        self.buffering = buffering
        self.ended = ended
        self.width = width
        self.height = height
        self.videoOutputs = videoOutputs
        self.volume = volume
        self.muted = muted
    }
}

public struct PlaybackTrack: Equatable, Sendable {
    public let id: Int32
    public let name: String
    public init(id: Int32, name: String) {
        self.id = id
        self.name = name
    }
}

/// Local operations only. Synchronization and UI policy belong to coordinators.
/// A returned command means submitted; observe supplies actual engine state.
public protocol PlaybackPort: Sendable {
    func load(_ localFile: URL, scope: PlaybackScope) async throws
    func observe(_ scope: PlaybackScope) async throws -> PlaybackObservation
    func setPaused(_ paused: Bool, scope: PlaybackScope) async throws
    func seek(to positionMs: Int64, scope: PlaybackScope) async throws
    func setRate(_ rate: Double, scope: PlaybackScope) async throws
    func setVolume(_ volume: Double, muted: Bool, scope: PlaybackScope) async throws
    func tracks(subtitles: Bool, scope: PlaybackScope) async throws -> [PlaybackTrack]
    func selectTrack(_ id: Int32, subtitles: Bool, scope: PlaybackScope) async throws
    func stop(_ scope: PlaybackScope) async throws
    func close() async
}

/// Local track controls that can acknowledge the engine's actual selection.
/// A returned ID of -1 means disabled/no active track.
public protocol PlaybackTrackControlPort: PlaybackPort {
    func selectedTrack(subtitles: Bool, scope: PlaybackScope) async throws -> Int32
}
