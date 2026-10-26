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
