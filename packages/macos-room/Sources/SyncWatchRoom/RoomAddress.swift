import Foundation

public enum RoomProtocolFailure: Error {
    case invalidRoomService, invalidRoomCredential, malformed, frameTooLarge, closed, transport
    case rejected(String)
}

/// Service origin only. Credentials never occur in a URL.
public struct RoomAddress: Sendable {
    public let origin: URL
    public init(_ value: String) throws {
        guard
            value.range(
                of: "\\Ahttps?://([A-Za-z0-9.-]+|\\[[0-9A-Fa-f:]+\\])(?::[0-9]{1,5})?/?\\z", options: .regularExpression
            ) != nil,
            !value.unicodeScalars.contains(where: { $0.value <= 32 || $0.value == 127 }), !value.contains("\\"),
            let parts = URLComponents(string: value), let url = parts.url,
            parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil,
            parts.path.isEmpty || parts.path == "/", let host = parts.host, !host.isEmpty,
            parts.scheme == "https" || (parts.scheme == "http" && ["127.0.0.1", "[::1]", "::1"].contains(host)),
            parts.port.map({ (1...65535).contains($0) }) ?? true
        else { throw RoomProtocolFailure.invalidRoomService }
        origin = url
    }
    func endpoint(_ path: String) -> URL { origin.appendingPathComponent(path) }
}

/// Memory-only credential, including when nested in diagnostic descriptions.
public struct RoomSecret: Sendable, CustomStringConvertible, CustomDebugStringConvertible {
    let value: String
    public init(_ value: String) throws {
        guard (32...256).contains(value.utf8.count), value.utf8.allSatisfy({ (33...126).contains($0) })
        else { throw RoomProtocolFailure.invalidRoomCredential }
        self.value = value
    }
    public var description: String { "[redacted]" }
    public var debugDescription: String { description }
    // Expose plaintext only for an explicit invitation transfer.
    public func copyInvitation() -> String { value }
}
