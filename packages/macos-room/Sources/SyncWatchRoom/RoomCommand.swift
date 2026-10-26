import Foundation
import SyncWatchDomain

public enum RoomWatchEndReason: String, Sendable { case user, finished }
public enum RoomCommandAction: Sendable {
    case catalog(batchID: String, offset: UInt64, items: [MediaDescriptor], final: Bool)
    case select(mediaID: String)
    case start(mediaID: String)
    case end(reason: RoomWatchEndReason)
    case missing(mediaID: String, missing: Bool)
    case meet(uri: String?)
}

/// Retain this value until the result is known. Retries reuse its original bytes.
/// The application owns monotonically increasing numbers for the membership.
public struct RoomCommand: Sendable {
    public let id: String
    public let encodedBytes: Data
    private let roomID: String
    private let memberID: String
    private let runID: String
    private let epoch: String

    public init(admission: RoomAdmission, number: UInt64, watchGeneration: UInt64, action: RoomCommandAction) throws {
        guard (1...RoomWire.maximumCounter).contains(number), watchGeneration <= RoomWire.maximumCounter,
            let member = admission.bootstrap.snapshot.members.first(where: { $0.memberID == admission.memberID })
        else { throw RoomProtocolFailure.malformed }
        roomID = admission.roomID
        memberID = admission.memberID
        runID = member.identity.clientRunID
        epoch = admission.bootstrap.snapshot.epoch
        for value in [roomID, memberID, runID, epoch] { try RoomWire.id(value) }
        id = "cmd-\(number)"
        let type: String
        let payload: [String: Any]
        switch action {
        case .catalog(let batch, let offset, let items, let final):
            try RoomWire.id(batch)
            guard items.count <= 100, offset <= RoomWire.maximumCounter - UInt64(items.count),
                Set(items.map(\.mediaID)).count == items.count
            else { throw RoomProtocolFailure.malformed }
            type = "catalog.updated"
            payload = ["batchId": batch, "offset": offset, "items": items.map(Self.media), "final": final]
        case .select(let mediaID), .start(let mediaID):
            try RoomWire.id(mediaID)
            if case .select = action { type = "selection.changed" } else { type = "watch.started" }
            payload = ["mediaId": mediaID]
        case .end(let reason):
            type = "watch.ended"
            payload = ["reason": reason.rawValue]
        case .missing(let mediaID, let missing):
            try RoomWire.id(mediaID)
            type = "media.missing"
            payload = ["mediaId": mediaID, "missing": missing]
        case .meet(let uri):
            try RoomWire.validateMeetURI(uri)
            type = "call.linkChanged"
            payload = ["meetUri": uri as Any? ?? NSNull()]
        }
        encodedBytes = try RoomWire.encode([
            "v": 1, "id": id, "type": type, "clientRunId": runID, "roomEpoch": epoch,
            "watchGeneration": watchGeneration, "payload": payload,
        ])
    }
    func verify(_ admission: RoomAdmission) throws {
        guard admission.roomID == roomID, admission.memberID == memberID,
            admission.bootstrap.snapshot.epoch == epoch,
            admission.bootstrap.snapshot.members.first(where: { $0.memberID == memberID })?.identity.clientRunID
                == runID
        else { throw RoomProtocolFailure.malformed }
    }
    private static func media(_ value: MediaDescriptor) -> [String: Any] {
        var fields: [String: Any] = [
            "v": 1, "mediaId": value.mediaID, "title": value.title, "titleKey": value.titleKey,
            "fileSizeBytes": value.fileSizeBytes, "durationMs": value.durationMs as Any? ?? NSNull(),
        ]
        if let hash = value.fullHashSha256 { fields["fullHashSha256"] = hash }
        return fields
    }
}

public struct RoomCommandResult: Sendable, Equatable {
    public let id: String
    public let sequence: UInt64
    public let errorCode: String?
    public static func decode(_ bytes: Data, command: RoomCommand) throws -> Self {
        let value = try RoomWire.object(bytes)
        try RoomWire.keys(value, ["v", "type", "id", "sequence", "error"])
        guard try RoomWire.integer(value["v"], maximum: 1) == 1, value["type"] as? String == "command.result",
            try RoomWire.string(value["id"]) == command.id
        else { throw RoomProtocolFailure.malformed }
        let error = try RoomWire.optionalString(value["error"])
        let allowed = [
            "foreignRun", "staleEpoch", "staleGeneration", "unavailable", "conflict", "queueFull",
            "invalidState", "forbidden", "malformed", "frameTooLarge",
        ]
        guard error.map({ allowed.contains($0) }) ?? true else { throw RoomProtocolFailure.malformed }
        return Self(id: command.id, sequence: try RoomWire.integer(value["sequence"]), errorCode: error)
    }
}
