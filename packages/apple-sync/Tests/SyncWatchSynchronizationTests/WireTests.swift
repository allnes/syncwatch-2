import Foundation
import SyncWatchDomain
import XCTest

@testable import SyncWatchSynchronization

final class WireTests: XCTestCase {
    func testSharedWireCorpus() throws {
        var root = URL(filePath: #filePath)
        for _ in 0..<5 { root.deleteLastPathComponent() }
        let data = try Data(contentsOf: root.appendingPathComponent("contracts/fixtures/native-session.json"))
        struct Fixture: Decodable {
            let name: String
            let json: String
            let accepted: Bool
        }
        let fixtures = try JSONDecoder().decode([Fixture].self, from: data)
        for fixture in fixtures {
            let accepted: Bool
            do {
                _ = try HelperWire.decode(
                    Data((fixture.json + "\n").utf8),
                    scope: PlaybackScope(clientRunID: "session-test", mediaGeneration: 2))
                accepted = true
            } catch { accepted = false }
            XCTAssertEqual(accepted, fixture.accepted, fixture.name)
        }
        XCTAssertEqual(fixtures.count, 30)
    }
}
