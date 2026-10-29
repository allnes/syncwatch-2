import Foundation

public enum WatchError: String, Error, Sendable {
    case invalidState
    case invalidLocalState
    case unsupportedVersion
}

public enum WatchPhase: String, Sendable {
    case idle, selected, preparing, active, ended
}

public struct WatchLoad: Equatable, Sendable {
    public let scope: PlaybackScope
    public let mediaID: String
    public let positionMs: Int64
}

/// Local resource work only. Neither effect is a peer playback command.
public enum WatchEffect: Equatable, Sendable {
    case load(WatchLoad)
    case release(PlaybackScope)
}

/// Serialize access in the application coordinator. Engine observations remain authoritative.
public struct WatchSession: Sendable {
    public static let maximumPositionMs: Int64 = 604_800_000
    public private(set) var scope: PlaybackScope
    public private(set) var phase: WatchPhase
    public private(set) var mediaID: String?
    public private(set) var positionMs: Int64
    public private(set) var paused = true
    public private(set) var playerPresented = false
    public private(set) var localState: LocalState

    public init(localState: LocalState = LocalState(), scope: PlaybackScope = .fresh()) throws {
        try localState.validate()
        self.localState = localState
        self.scope = scope
        mediaID = localState.selectedMediaID
        phase = mediaID == nil ? .idle : .selected
        positionMs = mediaID.map { localState.resumePosition(for: $0) } ?? 0
    }

    public mutating func select(_ mediaID: String, restartFromBeginning: Bool = false) throws -> [WatchEffect] {
        try Self.validateID(mediaID)
        guard restartFromBeginning || self.mediaID != mediaID else { return [] }
        let next = try scope.replacingMedia()
        let effects = releaseEffects
        scope = next
        self.mediaID = mediaID
        localState.selectedMediaID = mediaID
        positionMs = restartFromBeginning ? 0 : localState.resumePosition(for: mediaID)
        if restartFromBeginning { localState.resumePositions.removeAll { $0.mediaID == mediaID } }
        phase = .selected
        paused = true
        playerPresented = false
        return effects
    }

    /// Repeated Start/Continue cannot allocate duplicate media owners.
    public mutating func start() throws -> [WatchEffect] {
        guard let mediaID else { throw WatchError.invalidState }
        if phase == .active || phase == .preparing {
            playerPresented = true
            return []
        }
        let next = try scope.replacingMedia()
        scope = next
        phase = .preparing
        playerPresented = true
        paused = true
        return [.load(WatchLoad(scope: scope, mediaID: mediaID, positionMs: positionMs))]
    }

    /// Loading does not authorize playback; synchronization readiness is a separate adapter gate.
    public mutating func loaded(_ owner: PlaybackScope) throws {
        try check(owner, phase: .preparing)
        phase = .active
    }

    public mutating func recordPlayback(
        _ owner: PlaybackScope, positionMs: Int64, durationMs: Int64?, paused: Bool
    ) throws {
        try check(owner, phase: .active)
        guard (0...Self.maximumPositionMs).contains(positionMs),
            durationMs.map({ (0...Self.maximumPositionMs).contains($0) && positionMs <= $0 }) ?? true
        else { throw WatchError.invalidLocalState }
        let mediaID = self.mediaID!
        self.positionMs = positionMs
        self.paused = paused
        localState.resumePositions.removeAll { $0.mediaID == mediaID }
        localState.resumePositions.append(ResumePosition(mediaID: mediaID, positionMs: positionMs))
        if localState.resumePositions.count > 256 { localState.resumePositions.removeFirst() }
    }

    public mutating func returnToLibrary() { playerPresented = false }

    public mutating func continueWatching() throws {
        guard phase == .active || phase == .preparing else { throw WatchError.invalidState }
        playerPresented = true
    }

    public mutating func cancel(_ owner: PlaybackScope) throws -> [WatchEffect] {
        try check(owner, phase: .preparing)
        return try end()
    }

    public mutating func end() throws -> [WatchEffect] {
        guard phase == .preparing || phase == .active else { return [] }
        let next = try scope.replacingMedia()
        let effects = releaseEffects
        scope = next
        phase = .ended
        paused = true
        playerPresented = false
        return effects
    }

    public mutating func setPreferences(_ preferences: LocalPreferences) throws {
        try preferences.validate()
        localState.preferences = preferences
    }

    private var releaseEffects: [WatchEffect] {
        phase == .active || phase == .preparing ? [.release(scope)] : []
    }

    private func check(_ owner: PlaybackScope, phase expected: WatchPhase) throws {
        try scope.check(clientRunID: owner.clientRunID, mediaGeneration: owner.mediaGeneration)
        guard phase == expected else { throw WatchError.invalidState }
    }

    static func validateID(_ identifier: String) throws {
        _ = try PlaybackScope(clientRunID: identifier, mediaGeneration: 0)
    }
}
