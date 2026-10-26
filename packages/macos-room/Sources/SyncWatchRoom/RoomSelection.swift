import Foundation

/// The edition accepted at selection.changed, independent of subsequent catalog revisions.
public struct RoomSelectionDefinition: Sendable {
    public let epoch: String
    public let sequence: UInt64
    public let watchGeneration: UInt64
    public let selection: RoomCatalogEntry?

    public static func decode(_ bytes: Data, bootstrap: RoomBootstrap) throws -> Self {
        let value = try RoomWire.object(bytes)
        try RoomWire.keys(value, ["v", "roomEpoch", "sequence", "watchGeneration", "selection"])
        let sequence = try RoomWire.integer(value["sequence"])
        guard try RoomWire.integer(value["v"], maximum: 1) == 1,
            try RoomWire.string(value["roomEpoch"]) == bootstrap.snapshot.epoch,
            sequence >= bootstrap.snapshot.sequence,
            try RoomWire.integer(value["watchGeneration"]) == bootstrap.snapshot.watchGeneration
        else { throw RoomProtocolFailure.malformed }
        var selection: RoomCatalogEntry?
        if !(value["selection"] is NSNull) {
            let entry = try RoomWire.dictionary(value["selection"])
            try RoomWire.keys(entry, ["memberId", "media"])
            let member = try RoomWire.string(entry["memberId"])
            try RoomWire.id(member)
            // The publishing member may have left since the selection was accepted.
            selection = RoomCatalogEntry(memberID: member, media: try RoomMedia.decode(entry["media"]))
        }
        guard selection?.media.mediaID == bootstrap.snapshot.mediaID else { throw RoomProtocolFailure.malformed }
        return Self(
            epoch: bootstrap.snapshot.epoch, sequence: sequence,
            watchGeneration: bootstrap.snapshot.watchGeneration, selection: selection)
    }
}
