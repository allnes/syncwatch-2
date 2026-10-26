import Foundation

/// Local-only equality evidence. Never include the opaque stamp in room DTOs or logs.
public struct LoadedMediaVersion: Equatable, Sendable, CustomStringConvertible {
    public let scope: PlaybackScope
    public let sizeBytes: Int64
    private let stamp: String

    public init(scope: PlaybackScope, sizeBytes: Int64, stamp: String) throws {
        guard sizeBytes >= 0, stamp.utf8.count == 128,
            stamp.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) })
        else { throw ContractRejection.malformed }
        self.scope = scope
        self.sizeBytes = sizeBytes
        self.stamp = stamp
    }
    public var description: String { "LoadedMediaVersion(redacted)" }
}

/// Reads the player's owned input without resolving another path or moving its stream position.
public protocol LoadedMediaContentPort: Sendable {
    func contentVersion(_ scope: PlaybackScope) async throws -> LoadedMediaVersion
    func readContent(at offset: Int64, capacity: Int, scope: PlaybackScope) async throws -> Data
}
