import Foundation
import SyncWatchDomain

public struct RoomCatalogEntry: Sendable, Equatable {
    public let memberID: String
    public let media: MediaDescriptor
}

/// One bounded page of a bootstrap's stable catalog view, never a partial replacement catalog.
public struct RoomCatalogPage: Sendable {
    public let epoch: String
    public let sequence: UInt64
    public let items: [RoomCatalogEntry]
    public let nextCursor: String?

    public static func decode(_ bytes: Data, bootstrap: RoomBootstrap, cursor: String) throws -> Self {
        let position = try RoomCatalogPosition(cursor, bootstrap: bootstrap)
        let value = try RoomWire.object(bytes)
        try RoomWire.keys(value, ["v", "roomEpoch", "sequence", "items", "nextCursor"])
        guard try RoomWire.integer(value["v"], maximum: 1) == 1,
            try RoomWire.string(value["roomEpoch"]) == bootstrap.snapshot.epoch,
            try RoomWire.integer(value["sequence"]) == bootstrap.snapshot.sequence,
            let entries = value["items"] as? [[String: Any]], entries.count <= 100
        else { throw RoomProtocolFailure.malformed }
        let members = Set(bootstrap.snapshot.members.map(\.memberID))
        var seen = Set<String>()
        let items: [RoomCatalogEntry] = try entries.map { entry in
            try RoomWire.keys(entry, ["memberId", "media"])
            let member = try RoomWire.string(entry["memberId"])
            let media = try RoomWire.dictionary(entry["media"])
            var keys: Set<String> = ["v", "mediaId", "title", "titleKey", "fileSizeBytes", "durationMs"]
            if media["fullHashSha256"] != nil { keys.insert("fullHashSha256") }
            try RoomWire.keys(media, keys)
            guard members.contains(member), try RoomWire.integer(media["v"], maximum: 1) == 1 else {
                throw RoomProtocolFailure.malformed
            }
            let descriptor: MediaDescriptor
            do {
                descriptor = try MediaDescriptor(
                    mediaID: RoomWire.string(media["mediaId"]), title: RoomWire.string(media["title"]),
                    titleKey: RoomWire.string(media["titleKey"]),
                    fileSizeBytes: Int64(RoomWire.integer(media["fileSizeBytes"])),
                    durationMs: media["durationMs"] is NSNull ? nil : Int64(RoomWire.integer(media["durationMs"])),
                    fullHashSha256: media["fullHashSha256"].map { try RoomWire.string($0) })
            } catch { throw RoomProtocolFailure.malformed }
            // Both identifiers are ASCII and cannot contain the separator.
            guard seen.insert(member + ":" + descriptor.mediaID).inserted else { throw RoomProtocolFailure.malformed }
            return RoomCatalogEntry(memberID: member, media: descriptor)
        }
        let next = try RoomWire.optionalString(value["nextCursor"])
        if let next {
            let following = try RoomCatalogPosition(next, bootstrap: bootstrap)
            guard !items.isEmpty, following.offset == position.offset + UInt64(items.count) else {
                throw RoomProtocolFailure.malformed
            }
        }
        return Self(
            epoch: bootstrap.snapshot.epoch, sequence: bootstrap.snapshot.sequence, items: items, nextCursor: next)
    }
}

struct RoomCatalogPosition {
    let offset: UInt64
    init(_ cursor: String, bootstrap: RoomBootstrap) throws {
        func parse(_ value: String) throws -> (String, UInt64) {
            let parts = value.split(separator: ":", omittingEmptySubsequences: false)
            guard parts.count == 2,
                parts[1].range(of: "\\A(0|[1-9][0-9]{0,15})\\z", options: .regularExpression) != nil,
                let offset = UInt64(parts[1]), offset <= RoomWire.maximumCounter
            else { throw RoomProtocolFailure.malformed }
            try RoomWire.id(String(parts[0]))
            return (String(parts[0]), offset)
        }
        let initial = try parse(bootstrap.catalogCursor)
        let current = try parse(cursor)
        guard initial.1 == 0, initial.0 == current.0 else { throw RoomProtocolFailure.malformed }
        offset = current.1
    }
}
