import Foundation
import XCTest

@testable import SyncWatchRoom

private actor CatalogResponses {
    let pages: [Data]
    var index = 0
    init(_ pages: [Data]) { self.pages = pages }
    func fetch(_ cursor: String) throws -> Data {
        guard index < pages.count else { throw RoomProtocolFailure.transport }
        let expected: String
        if index == 0 {
            expected = "view-1:0"
        } else {
            let previous = try RoomWire.object(pages[index - 1])
            expected = try RoomWire.string(previous["nextCursor"])
        }
        guard cursor == expected else { throw RoomProtocolFailure.malformed }
        defer { index += 1 }
        return pages[index]
    }
}

final class RoomCatalogViewTests: XCTestCase {
    func testCompleteViewsAndFailureBoundaries() async throws {
        let fixture = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("../../../../contracts/fixtures/room-client.json").standardized
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: fixture)) as? [String: Any])
        let bootstrap = try RoomBootstrap.decode(Data(RoomWire.string(root["catalogBootstrap"]).utf8))
        for item in try XCTUnwrap(root["catalogViews"] as? [[String: Any]]) {
            let name = try XCTUnwrap(item["name"] as? String)
            let valid = try XCTUnwrap(item["valid"] as? Bool)
            let pages = try XCTUnwrap(item["pages"] as? [String]).map { Data($0.utf8) }
            let source = CatalogResponses(pages)
            do {
                let result = try await RoomCatalogView.read(bootstrap: bootstrap) { try await source.fetch($0) }
                XCTAssertTrue(valid, name)
                XCTAssertEqual(result.bootstrap, bootstrap, name)
                XCTAssertEqual(result.items.count, item["count"] as? Int, name)
                let calls = await source.index
                XCTAssertEqual(calls, pages.count, name)
            } catch RoomProtocolFailure.malformed { XCTAssertFalse(valid, name) }
        }
        for count in [2048, 2049] {
            let pages = try stride(from: 0, to: count, by: 100).map { start in
                let end = min(start + 100, count)
                return try RoomWire.encode([
                    "v": 1, "roomEpoch": "epoch-room", "sequence": 7,
                    "items": (start..<end).map { index in
                        [
                            "memberId": "member-owner",
                            "media": [
                                "v": 1, "mediaId": "movie-\(index)", "title": "Movie", "titleKey": "movie",
                                "fileSizeBytes": 1024, "durationMs": NSNull(),
                            ],
                        ] as [String: Any]
                    },
                    "nextCursor": end < count ? "view-1:\(end)" as Any : NSNull(),
                ])
            }
            let source = CatalogResponses(pages)
            do {
                let result = try await RoomCatalogView.read(bootstrap: bootstrap) { try await source.fetch($0) }
                XCTAssertEqual(count, 2048)
                XCTAssertEqual(result.items.count, count)
            } catch RoomProtocolFailure.malformed { XCTAssertEqual(count, 2049) }
        }
        let terminal = try RoomWire.encode([
            "v": 1, "roomEpoch": "epoch-room", "sequence": 7, "items": [], "nextCursor": NSNull(),
        ])
        let cancelled = Task {
            try await RoomCatalogView.read(bootstrap: bootstrap) { _ in
                withUnsafeCurrentTask { $0?.cancel() }
                return terminal
            }
        }
        do {
            _ = try await cancelled.value
            XCTFail("Cancelled final page escaped")
        } catch is CancellationError {}
        do {
            _ = try await RoomCatalogView.read(bootstrap: bootstrap) { _ in
                throw RoomProtocolFailure.rejected("snapshotRequired")
            }
            XCTFail("Expired cursor returned a partial view")
        } catch RoomProtocolFailure.rejected("snapshotRequired") {}
    }
}
