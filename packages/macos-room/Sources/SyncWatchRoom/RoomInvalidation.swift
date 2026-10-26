import Foundation

/// An ordered hint to fetch an authoritative snapshot. Payload data is never applied as state.
public struct RoomInvalidation: Sendable {
    public let epoch: String
    public let sequence: UInt64
    public static func decode(_ bytes: Data) throws -> Self {
        let value = try RoomWire.object(bytes)
        try RoomWire.keys(
            value, ["v", "type", "roomEpoch", "sequence", "memberId", "clientRunId", "watchGeneration", "payload"])
        guard try RoomWire.integer(value["v"], maximum: 1) == 1,
            [
                "member.bound", "member.left", "catalog.updated", "selection.changed", "watch.started", "watch.ended",
                "media.missing", "call.linkChanged",
            ].contains(try RoomWire.string(value["type"]))
        else { throw RoomProtocolFailure.malformed }
        let epoch = try RoomWire.string(value["roomEpoch"])
        try RoomWire.id(epoch)
        try RoomWire.id(RoomWire.string(value["memberId"]))
        try RoomWire.id(RoomWire.string(value["clientRunId"]))
        _ = try RoomWire.integer(value["watchGeneration"])
        _ = try RoomWire.dictionary(value["payload"])
        return Self(epoch: epoch, sequence: try RoomWire.integer(value["sequence"]))
    }
}
