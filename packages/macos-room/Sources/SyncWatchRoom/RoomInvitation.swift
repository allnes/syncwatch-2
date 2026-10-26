import Foundation

/// Explicit clipboard transfer. Parsing never connects to a service or persists a credential.
public struct RoomInvitation: Sendable, CustomStringConvertible, CustomDebugStringConvertible {
    public let roomID: String
    public let credential: RoomSecret
    public init(roomID: String, credential: RoomSecret) throws {
        try RoomWire.id(roomID)
        self.roomID = roomID
        self.credential = credential
    }
    public static func parse(_ text: String) throws -> Self {
        guard text.utf8.count <= RoomWire.maximumBytes else { throw RoomProtocolFailure.frameTooLarge }
        let lines = text.replacingOccurrences(of: "\r\n", with: "\n").components(separatedBy: "\n")
        guard lines.count == 2 else { throw RoomProtocolFailure.malformed }
        return try Self(roomID: lines[0], credential: RoomSecret(lines[1]))
    }
    public func copyText() -> String { roomID + "\n" + credential.copyInvitation() }
    public var description: String { "[redacted invitation]" }
    public var debugDescription: String { description }
}
