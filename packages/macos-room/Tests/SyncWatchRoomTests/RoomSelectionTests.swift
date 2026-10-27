import Foundation
import XCTest

@testable import SyncWatchRoom

final class RoomSelectionTests: XCTestCase {
    func testSharedFrozenSelectionCorpus() throws {
        let fixture = URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent(
            "../../../../contracts/fixtures/room-selection.json"
        ).standardized
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: fixture)) as? [String: Any])
        for entry in try XCTUnwrap(root["cases"] as? [[String: Any]]) {
            let name = try XCTUnwrap(entry["name"] as? String)
            let bootstrap = try RoomBootstrap.decode(Data(try XCTUnwrap(entry["bootstrap"] as? String).utf8))
            let wire = Data(try XCTUnwrap(entry["wire"] as? String).utf8)
            if try XCTUnwrap(entry["valid"] as? Bool) {
                let result = try RoomSelectionDefinition.decode(wire, bootstrap: bootstrap)
                XCTAssertEqual(result.selection?.media.mediaID, bootstrap.snapshot.mediaID, name)
                XCTAssertEqual(result.watchGeneration, bootstrap.snapshot.watchGeneration, name)
                if let selection = result.selection {
                    XCTAssertEqual(selection.memberID, "departed-member", name)
                    XCTAssertEqual(selection.media.fileSizeBytes, 1000, name)
                }
            } else {
                XCTAssertThrowsError(try RoomSelectionDefinition.decode(wire, bootstrap: bootstrap), name)
            }
        }
    }
}
