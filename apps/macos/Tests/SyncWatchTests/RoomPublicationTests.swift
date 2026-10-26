import Foundation
import SyncWatchDomain
import SyncWatchLibrary
import SyncWatchRoom
import Testing

@testable import SyncWatch

@MainActor @Test func roomPublicationKeepsLocalIdentityAndBoundsWireBatches() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    try Data("authored metadata fixture".utf8).write(to: directory.appendingPathComponent("Movie.mkv"))
    let files = try await FileSystemLibrary().scan(
        root: directory, rootID: UUID().uuidString.lowercased(), recursive: false)
    let map = RoomLocalCatalog()
    let publication = try map.prepare(files)
    let id = try #require(publication.items.first?.mediaID)
    #expect(id != files.first?.id && publication.items.first?.title == "Movie")
    #expect(try map.prepare(files).items.first?.mediaID == id)
    #expect(map.localID(for: id) == nil)
    map.acknowledge(publication)
    #expect(map.localID(for: id) == files.first?.id)
    #expect(try RoomLocalCatalog().prepare(files).items.first?.mediaID != id)
    let empty = try map.prepare([])
    map.acknowledge(empty)
    #expect(map.localID(for: id) == nil)

    let fixture = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .appendingPathComponent("../../../../contracts/fixtures/room-client.json").standardized
    let root = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: fixture)) as? [String: Any])
    let admissionCase = try #require(
        (root["admissions"] as? [[String: Any]])?.first {
            ($0["valid"] as? Bool) == true && ($0["owner"] as? Bool) == true
        })
    let admission = try RoomAdmission.decode(
        Data(try #require(admissionCase["wire"] as? String).utf8),
        identity: RoomIdentity(clientRunID: "run-room-client", syncplayUsername: "Room User"), owner: true)
    let title = String(repeating: "😀", count: 256)
    let items = try (0..<100).map { index in
        try MediaDescriptor(
            mediaID: "movie-\(index)", title: title, titleKey: title, fileSizeBytes: 1024, durationMs: nil,
            fullHashSha256: nil)
    }
    var offset = 0
    var number: UInt64 = 1
    repeat {
        let batch = try RoomMembershipSession.catalogCommand(
            admission: admission, number: number, generation: 0, batch: "batch-test", items: items, offset: offset)
        #expect((1...100).contains(batch.count) && batch.command.encodedBytes.count <= 65536)
        let wire = try #require(JSONSerialization.jsonObject(with: batch.command.encodedBytes) as? [String: Any])
        let payload = try #require(wire["payload"] as? [String: Any])
        #expect(payload["offset"] as? Int == offset)
        #expect((payload["items"] as? [[String: Any]])?.count == batch.count)
        #expect(payload["final"] as? Bool == (offset + batch.count == items.count))
        offset += batch.count
        number += 1
    } while offset < items.count
    #expect(number > 2 && offset == 100)
    let clear = try RoomMembershipSession.catalogCommand(
        admission: admission, number: number, generation: 0, batch: "batch-empty", items: [], offset: 0)
    #expect(clear.count == 0)
}
