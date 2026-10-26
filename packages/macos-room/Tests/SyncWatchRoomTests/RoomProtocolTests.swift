import Foundation
import XCTest

@testable import SyncWatchRoom

final class RoomProtocolTests: XCTestCase {
    func testSharedAdmissionAndAddressCorpus() throws {
        let fixture = URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent(
            "../../../../contracts/fixtures/room-client.json"
        ).standardized
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: fixture)) as? [String: Any])
        let identity = try RoomIdentity(clientRunID: "run-room-client", syncplayUsername: "Room User")
        let bootstrap = try RoomBootstrap.decode(Data(try XCTUnwrap(root["catalogBootstrap"] as? String).utf8))
        for entry in try XCTUnwrap(root["catalogs"] as? [[String: Any]]) {
            let name = try XCTUnwrap(entry["name"] as? String)
            let wire = Data(try XCTUnwrap(entry["wire"] as? String).utf8)
            let cursor = try XCTUnwrap(entry["cursor"] as? String)
            if try XCTUnwrap(entry["valid"] as? Bool) {
                let page = try RoomCatalogPage.decode(wire, bootstrap: bootstrap, cursor: cursor)
                XCTAssertEqual(page.epoch, bootstrap.snapshot.epoch, name)
                XCTAssertEqual(page.sequence, bootstrap.snapshot.sequence, name)
                XCTAssertEqual(page.items.count, entry["count"] as? Int, name)
                XCTAssertEqual(page.nextCursor, entry["nextCursor"] as? String, name)
            } else {
                XCTAssertThrowsError(try RoomCatalogPage.decode(wire, bootstrap: bootstrap, cursor: cursor), name)
            }
        }
        for entry in try XCTUnwrap(root["invitations"] as? [[String: Any]]) {
            let name = try XCTUnwrap(entry["name"] as? String)
            let text = try XCTUnwrap(entry["text"] as? String)
            if try XCTUnwrap(entry["valid"] as? Bool) {
                let invitation = try RoomInvitation.parse(text)
                let roomID = try XCTUnwrap(entry["roomID"] as? String)
                let credential = try XCTUnwrap(entry["credential"] as? String)
                XCTAssertEqual(invitation.roomID, roomID, name)
                XCTAssertEqual(invitation.copyText(), roomID + "\n" + credential, name)
                XCTAssertFalse(String(reflecting: invitation).contains(credential), name)
            } else {
                XCTAssertThrowsError(try RoomInvitation.parse(text), name)
            }
        }
        for entry in try XCTUnwrap(root["addresses"] as? [[String: Any]]) {
            let value = try XCTUnwrap(entry["value"] as? String)
            let valid = try XCTUnwrap(entry["valid"] as? Bool)
            if valid {
                XCTAssertNoThrow(try RoomAddress(value), value)
            } else {
                XCTAssertThrowsError(try RoomAddress(value), value)
            }
        }
        for entry in try XCTUnwrap(root["admissions"] as? [[String: Any]]) {
            let name = try XCTUnwrap(entry["name"] as? String)
            let data = Data(try XCTUnwrap(entry["wire"] as? String).utf8)
            let valid = try XCTUnwrap(entry["valid"] as? Bool)
            let owner = try XCTUnwrap(entry["owner"] as? Bool)
            if valid {
                let admission = try RoomAdmission.decode(data, identity: identity, owner: owner)
                XCTAssertEqual(admission.memberID, "member-owner", name)
                XCTAssertEqual(admission.bootstrap.connection.port, 8999, name)
                XCTAssertFalse(String(reflecting: admission).contains(String(repeating: "A", count: 64)), name)
                XCTAssertFalse(String(reflecting: admission).contains(String(repeating: "B", count: 64)), name)
            } else {
                XCTAssertThrowsError(try RoomAdmission.decode(data, identity: identity, owner: owner), name)
            }
        }
    }
}
