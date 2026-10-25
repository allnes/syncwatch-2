public enum CorrectionDisposition: String, Sendable {
    case apply, waitForUserObservation, cancelled, unavailable
}

/// Native command ordering only. Syncplay still owns timing and correction policy.
/// Serialize access in the owner. Send an actual user observation before marking
/// its sequence published; only then can cancellation be proved to the helper.
public struct PlaybackActionFence: Sendable {
    public let scope: PlaybackScope
    public private(set) var issuedSequence: UInt64 = 0
    public private(set) var publishedSequence: UInt64 = 0
    public private(set) var invalidated = false

    public init(scope: PlaybackScope) { self.scope = scope }

    public mutating func beginUserAction(_ owner: PlaybackScope) throws -> UInt64 {
        try check(owner)
        guard issuedSequence < PlaybackScope.maximumGeneration else { throw ContractRejection.malformed }
        issuedSequence += 1
        return issuedSequence
    }

    /// Recheck on the serialized writer immediately before emitting a user frame.
    public func canPublish(_ sequence: UInt64, owner: PlaybackScope) throws -> Bool {
        try check(owner)
        guard sequence > 0, sequence <= issuedSequence else { throw ContractRejection.malformed }
        return sequence > publishedSequence
    }

    @discardableResult public mutating func didPublish(_ sequence: UInt64, observation: PlaybackObservation) throws
        -> Bool
    {
        guard try canPublish(sequence, owner: observation.scope) else { return false }
        guard observation.status == .ready else { throw WatchError.invalidState }
        publishedSequence = sequence
        return true
    }

    /// Check before queuing a correction and after its native await. A pending
    /// local action must publish its actual state before a cancelled reply.
    public func correction(_ owner: PlaybackScope, afterUserAction: UInt64) throws -> CorrectionDisposition {
        try scope.check(clientRunID: owner.clientRunID, mediaGeneration: owner.mediaGeneration)
        if invalidated { return .unavailable }
        guard afterUserAction <= publishedSequence else { throw ContractRejection.malformed }
        if afterUserAction < publishedSequence { return .cancelled }
        return issuedSequence == publishedSequence ? .apply : .waitForUserObservation
    }

    public mutating func invalidate() { invalidated = true }
    private func check(_ owner: PlaybackScope) throws {
        try scope.check(clientRunID: owner.clientRunID, mediaGeneration: owner.mediaGeneration)
        guard !invalidated else { throw WatchError.invalidState }
    }
}
