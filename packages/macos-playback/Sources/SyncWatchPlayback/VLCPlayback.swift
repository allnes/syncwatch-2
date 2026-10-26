import Foundation
import SyncWatchDomain
import SyncWatchPlaybackNative

// Mutable pointer access is confined to VLCPlayback. The Sendable box permits
// asynchronous fallback disposal if a caller omitted explicit close.
private final class NativeOwner: @unchecked Sendable {
    var pointer: OpaquePointer?
    func close() {
        if let pointer {
            sw_playback_close(pointer)
            self.pointer = nil
        }
    }
}

private final class RuntimeOwner: @unchecked Sendable {
    var pointer: OpaquePointer?
    func close() {
        if let pointer {
            sw_runtime_close(pointer)
            self.pointer = nil
        }
    }
}

/// One application owns the plugin bank; ending a movie releases only that movie's player.
public actor VLCPlaybackRuntime {
    private let owner = RuntimeOwner()
    private var closed = false
    public init() {}
    public func open(package: URL) throws {
        guard !closed, owner.pointer == nil else { throw PlaybackFailure.closed }
        let runtime = try MediaRuntime(package: package)
        guard sw_runtime_open(runtime.library.path, runtime.revision, 1, &owner.pointer) == 0 else {
            throw PlaybackFailure.unavailable
        }
    }
    fileprivate func makePlayer(surface: UInt) throws -> NativeOwner {
        guard !closed, let pointer = owner.pointer else { throw PlaybackFailure.closed }
        let result = NativeOwner()
        guard sw_playback_open_runtime(pointer, UnsafeMutableRawPointer(bitPattern: surface), 0, &result.pointer) == 0
        else { throw PlaybackFailure.engine }
        return result
    }
    public func close() {
        closed = true
        owner.close()
    }
    deinit {
        let runtime = owner
        Task.detached { runtime.close() }
    }
}

public actor VLCPlayback: PlaybackPort, LoadedMediaContentPort {
    private var owner = NativeOwner()
    private var scope: PlaybackScope?
    private var closed = false

    public init() {}

    public func open(runtime: VLCPlaybackRuntime, appKitSurfaceAddress: UInt) async throws {
        guard !closed, owner.pointer == nil else { throw PlaybackFailure.closed }
        let prepared = try await runtime.makePlayer(surface: appKitSurfaceAddress)
        guard !closed, owner.pointer == nil else {
            prepared.close()
            throw PlaybackFailure.closed
        }
        owner = prepared
    }

    /// Call from a coordinator; retain the native view until close completes.
    /// The actor executor performs blocking native work away from the UI actor.
    public func open(package: URL, appKitSurfaceAddress: UInt? = nil) throws {
        guard !closed, owner.pointer == nil else { throw PlaybackFailure.closed }
        let runtime = try MediaRuntime(package: package)
        let surface = appKitSurfaceAddress.flatMap(UnsafeMutableRawPointer.init(bitPattern:))
        try check(
            sw_playback_open(
                runtime.library.path, runtime.revision,
                surface == nil ? 0 : 1, surface, &owner.pointer))
    }

    public func load(_ localFile: URL, scope incoming: PlaybackScope) throws {
        guard localFile.isFileURL, localFile.host == nil || localFile.host == "",
            try localFile.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true
        else { throw PlaybackFailure.invalid }
        if let scope {
            guard scope.clientRunID == incoming.clientRunID else { throw ContractRejection.foreignRun }
            guard incoming.mediaGeneration > scope.mediaGeneration else { throw ContractRejection.staleGeneration }
        }
        let pointer = try native()
        let result = sw_playback_load(pointer, incoming.mediaGeneration, localFile.path)
        if result == 0 || result == 4 { scope = incoming }
        try check(result)
    }

    public func contentVersion(_ scope: PlaybackScope) throws -> LoadedMediaVersion {
        var value = sw_input_version()
        try check(sw_playback_input_version(native(scope), scope.mediaGeneration, &value))
        let words = withUnsafeBytes(of: value.words) { Array($0.bindMemory(to: UInt64.self)) }
        guard words.count == 8, words[3] <= UInt64(Int64.max) else { throw PlaybackFailure.engine }
        let stamp = words.map { String(format: "%016llx", $0) }.joined()
        return try LoadedMediaVersion(scope: scope, sizeBytes: Int64(words[3]), stamp: stamp)
    }
    public func readContent(at offset: Int64, capacity: Int, scope: PlaybackScope) throws -> Data {
        guard offset >= 0, (1...262_144).contains(capacity) else { throw PlaybackFailure.invalid }
        var buffer = [UInt8](repeating: 0, count: capacity)
        var count = 0
        try check(sw_playback_read_at(native(scope), scope.mediaGeneration, UInt64(offset), &buffer, capacity, &count))
        try Task.checkCancellation()
        guard (0...capacity).contains(count) else { throw PlaybackFailure.engine }
        return Data(buffer.prefix(count))
    }
    public func observe(_ scope: PlaybackScope) throws -> PlaybackObservation {
        let pointer = try native(scope)
        var value = sw_observation()
        try check(sw_playback_observe(pointer, scope.mediaGeneration, &value))
        guard let status = PlaybackStatus(rawValue: value.status) else { throw PlaybackFailure.engine }
        return try PlaybackObservation(
            scope: scope, sequence: value.sequence, status: status, positionMs: value.position_ms,
            durationMs: value.duration_ms < 0 ? nil : value.duration_ms, paused: value.paused != 0,
            rate: value.rate, seekable: value.seekable != 0, buffering: value.buffering != 0,
            ended: value.ended != 0, width: Int(value.width), height: Int(value.height),
            videoOutputs: Int(value.video_outputs),
            volume: value.volume < 0 ? nil : Double(min(100, value.volume)) / 100,
            muted: value.muted != 0)
    }

    public func setPaused(_ paused: Bool, scope: PlaybackScope) throws {
        try check(sw_playback_pause(native(scope), scope.mediaGeneration, paused ? 1 : 0))
    }
    public func seek(to positionMs: Int64, scope: PlaybackScope) throws {
        try check(sw_playback_seek(native(scope), scope.mediaGeneration, positionMs))
    }
    public func setRate(_ rate: Double, scope: PlaybackScope) throws {
        try check(sw_playback_rate(native(scope), scope.mediaGeneration, rate))
    }
    public func setVolume(_ volume: Double, muted: Bool, scope: PlaybackScope) throws {
        try check(sw_playback_volume(native(scope), scope.mediaGeneration, volume, muted ? 1 : 0))
    }
    public func tracks(subtitles: Bool, scope: PlaybackScope) throws -> [PlaybackTrack] {
        let pointer = try native(scope)
        var ids = [Int32](repeating: 0, count: 256)
        var count = 0
        try check(sw_playback_tracks(pointer, scope.mediaGeneration, subtitles ? 1 : 0, &ids, ids.count, &count))
        return try ids.prefix(count).map { id in
            var name = [CChar](repeating: 0, count: 65_536)
            try check(sw_playback_track_name(pointer, scope.mediaGeneration, subtitles ? 1 : 0, id, &name, name.count))
            let bytes = name.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }
            guard let text = String(bytes: bytes, encoding: .utf8) else { throw PlaybackFailure.engine }
            return PlaybackTrack(id: id, name: text)
        }
    }
    public func selectTrack(_ id: Int32, subtitles: Bool, scope: PlaybackScope) throws {
        try check(sw_playback_select_track(native(scope), scope.mediaGeneration, subtitles ? 1 : 0, id))
    }
    public func stop(_ scope: PlaybackScope) throws {
        try check(sw_playback_stop(native(scope), scope.mediaGeneration))
    }
    public func close() {
        closed = true
        owner.close()
    }
    private func native(_ incoming: PlaybackScope? = nil) throws -> OpaquePointer {
        // Check on the actor executor, before any scoped native operation starts.
        // Terminal close intentionally bypasses this cancellable command path.
        try Task.checkCancellation()
        guard !closed, let pointer = owner.pointer else { throw PlaybackFailure.closed }
        if let incoming {
            guard let scope else { throw PlaybackFailure.unavailable }
            try scope.check(clientRunID: incoming.clientRunID, mediaGeneration: incoming.mediaGeneration)
        }
        return pointer
    }
    private func check(_ code: Int32) throws {
        switch code {
        case 0: return
        case 1: throw PlaybackFailure.invalid
        case 2: throw PlaybackFailure.unavailable
        case 3: throw PlaybackFailure.stale
        default: throw PlaybackFailure.engine
        }
    }
    deinit {
        let nativeOwner = owner
        Task.detached { nativeOwner.close() }
    }
}
