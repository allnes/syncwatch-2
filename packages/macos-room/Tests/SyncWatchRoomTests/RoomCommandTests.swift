import Foundation
import SyncWatchDomain
import XCTest

@testable import SyncWatchRoom

final class RoomCommandTests: XCTestCase, @unchecked Sendable {
    private func fixture() throws -> ([String: Any], RoomAdmission) {
        let path = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("../../../../contracts/fixtures/room-client.json").standardized
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: path)) as? [String: Any])
        let entry = try XCTUnwrap((root["admissions"] as? [[String: Any]])?.first { $0["valid"] as? Bool == true })
        return (
            root,
            try RoomAdmission.decode(
                Data(try XCTUnwrap(entry["wire"] as? String).utf8),
                identity: RoomIdentity(clientRunID: "run-room-client", syncplayUsername: "Room User"), owner: true)
        )
    }
    private func action(_ entry: [String: Any]) throws -> RoomCommandAction {
        let payload = try XCTUnwrap(entry["payload"] as? [String: Any])
        switch try XCTUnwrap(entry["type"] as? String) {
        case "catalog.updated":
            let items = try XCTUnwrap(payload["items"] as? [[String: Any]]).map { item in
                try MediaDescriptor(
                    mediaID: XCTUnwrap(item["mediaId"] as? String), title: XCTUnwrap(item["title"] as? String),
                    titleKey: XCTUnwrap(item["titleKey"] as? String),
                    fileSizeBytes: XCTUnwrap(item["fileSizeBytes"] as? NSNumber).int64Value,
                    durationMs: (item["durationMs"] as? NSNumber)?.int64Value,
                    fullHashSha256: item["fullHashSha256"] as? String)
            }
            return .catalog(
                batchID: try XCTUnwrap(payload["batchId"] as? String),
                offset: try XCTUnwrap(payload["offset"] as? NSNumber).uint64Value,
                items: items, final: try XCTUnwrap(payload["final"] as? Bool))
        case "selection.changed": return .select(mediaID: try XCTUnwrap(payload["mediaId"] as? String))
        case "watch.started": return .start(mediaID: try XCTUnwrap(payload["mediaId"] as? String))
        case "watch.ended":
            return .end(reason: try XCTUnwrap(RoomWatchEndReason(rawValue: XCTUnwrap(payload["reason"] as? String))))
        case "media.missing":
            return .missing(
                mediaID: try XCTUnwrap(payload["mediaId"] as? String),
                missing: try XCTUnwrap(payload["missing"] as? Bool))
        case "call.linkChanged": return .meet(uri: payload["meetUri"] as? String)
        default: throw RoomProtocolFailure.malformed
        }
    }
    func testSharedCommandsResultsAndRetainedBytes() throws {
        let (root, admission) = try fixture()
        let corpus = try XCTUnwrap(root["commands"] as? [String: Any])
        for entry in try XCTUnwrap(corpus["outgoing"] as? [[String: Any]]) {
            let name = try XCTUnwrap(entry["name"] as? String)
            func make() throws -> RoomCommand {
                try RoomCommand(
                    admission: admission, number: XCTUnwrap(entry["number"] as? NSNumber).uint64Value,
                    watchGeneration: XCTUnwrap(entry["generation"] as? NSNumber).uint64Value, action: action(entry))
            }
            if try XCTUnwrap(entry["valid"] as? Bool) {
                let command = try make()
                let original = command.encodedBytes
                var copy = original
                copy[0] ^= 1
                XCTAssertEqual(command.encodedBytes, original, name)
                let actual = try XCTUnwrap(JSONSerialization.jsonObject(with: original) as? NSDictionary)
                let expected: [String: Any] = [
                    "v": 1, "id": command.id, "type": entry["type"]!,
                    "clientRunId": "run-room-client", "roomEpoch": "epoch-room",
                    "watchGeneration": entry["generation"]!, "payload": entry["payload"]!,
                ]
                XCTAssertTrue(actual.isEqual(to: expected), name)
            } else {
                XCTAssertThrowsError(try make(), name)
            }
        }
        let command = try RoomCommand(
            admission: admission, number: 1, watchGeneration: 0, action: .select(mediaID: "movie-a"))
        for entry in try XCTUnwrap(corpus["results"] as? [[String: Any]]) {
            let data = Data(try XCTUnwrap(entry["wire"] as? String).utf8)
            let name = try XCTUnwrap(entry["name"] as? String)
            if try XCTUnwrap(entry["valid"] as? Bool) {
                let result = try RoomCommandResult.decode(data, command: command)
                XCTAssertEqual(result.id, "cmd-1", name)
                XCTAssertEqual(result.sequence, 7, name)
                let expected = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
                XCTAssertEqual(result.errorCode, expected["error"] as? String, name)
            } else {
                XCTAssertThrowsError(try RoomCommandResult.decode(data, command: command), name)
            }
        }
        func media(_ index: Int, title: String) throws -> MediaDescriptor {
            try MediaDescriptor(
                mediaID: "movie-\(index)", title: title, titleKey: MediaDescriptor.normalizedTitleKey(title),
                fileSizeBytes: 1, durationMs: nil, fullHashSha256: nil)
        }
        let oversized = try (0..<100).map { try media($0, title: String(repeating: "😀", count: 256)) }
        XCTAssertThrowsError(
            try RoomCommand(
                admission: admission, number: 1, watchGeneration: 0,
                action: .catalog(batchID: "batch-a", offset: 0, items: oversized, final: true)))
        let tooMany = try (0..<101).map { try media($0, title: "Movie") }
        XCTAssertThrowsError(
            try RoomCommand(
                admission: admission, number: 1, watchGeneration: 0,
                action: .catalog(batchID: "batch-a", offset: 0, items: tooMany, final: true)))
    }
    func testForeignMembershipIsRejectedBeforeTransport() async throws {
        let (_, admission) = try fixture()
        let command = try RoomCommand(
            admission: admission, number: 1, watchGeneration: 0, action: .select(mediaID: "movie-a"))
        let foreign = RoomAdmission(
            roomID: "room-other", memberID: admission.memberID, token: admission.token,
            invitation: admission.invitation, expiresAt: admission.expiresAt, bootstrap: admission.bootstrap)
        let client = try RoomClient(address: RoomAddress("http://127.0.0.1:1"))
        do {
            _ = try await client.execute(foreign, command: command)
            XCTFail("Foreign membership reached transport")
        } catch RoomProtocolFailure.malformed {} catch { XCTFail("Unexpected failure: \(error)") }
        await client.close()
    }
}
