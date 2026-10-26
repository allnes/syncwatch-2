import Foundation
import SyncWatchDomain
import XCTest

@testable import SyncWatchRoom

final class RoomCommandTransportTests: XCTestCase, @unchecked Sendable {
    func testNativeMetadataCommands() async throws {
        let environment = ProcessInfo.processInfo.environment
        guard let address = environment["SYNCWATCH_ROOM_SERVICE"], let key = environment["SYNCWATCH_ROOM_CREATION_KEY"]
        else { throw XCTSkip("Requires an owned Room metadata service") }
        let owner = try RoomClient(address: RoomAddress(address))
        let guest = try RoomClient(address: RoomAddress(address))
        do {
            let admission = try await owner.create(
                identity: RoomIdentity(clientRunID: "run-" + UUID().uuidString, syncplayUsername: "macOS commands"),
                connection: RoomConnection(host: "syncplay.example.com", port: 8999, room: "Commands check"),
                creationKey: RoomSecret(key))
            let events = try await owner.openEvents(admission)
            _ = try RoomBootstrap.initialEvent(await events.receive(), admission: admission)
            let catalog = try (0..<250).map { index in
                try MediaDescriptor(
                    mediaID: "movie-\(index)", title: "Movie \(index)", titleKey: "movie \(index)",
                    fileSizeBytes: Int64(1024 + index),
                    durationMs: 60000, fullHashSha256: String(format: "%064llx", UInt64(index)))
            }
            for index in 0..<3 {
                let command = try RoomCommand(
                    admission: admission, number: UInt64(index + 1), watchGeneration: 0,
                    action: .catalog(
                        batchID: "batch-native", offset: UInt64(index * 100),
                        items: Array(catalog.dropFirst(index * 100).prefix(100)), final: index == 2))
                let first = try await owner.execute(admission, command: command)
                let replay = try await owner.execute(admission, command: command)
                XCTAssertNil(first.errorCode)
                XCTAssertEqual(first, replay)
                if index == 0 {
                    let partial = try await owner.snapshot(admission)
                    let page = try await owner.catalog(admission, bootstrap: partial, cursor: partial.catalogCursor)
                    XCTAssertTrue(page.items.isEmpty)
                }
            }
            let view = try await owner.snapshot(admission)
            var cursor: String? = view.catalogCursor
            var ids = Set<String>()
            while let current = cursor {
                let page = try await owner.catalog(admission, bootstrap: view, cursor: current)
                for item in page.items {
                    XCTAssertEqual(item.memberID, admission.memberID)
                    XCTAssertTrue(ids.insert(item.media.mediaID).inserted)
                }
                cursor = page.nextCursor
            }
            XCTAssertEqual(ids, Set(catalog.map(\.mediaID)))
            let selection = try RoomCommand(
                admission: admission, number: 4, watchGeneration: 0, action: .select(mediaID: "movie-0"))
            let selected = try await owner.execute(admission, command: selection)
            let replay = try await owner.execute(admission, command: selection)
            XCTAssertNil(selected.errorCode)
            XCTAssertEqual(selected, replay)
            do {
                _ = try await owner.execute(
                    admission,
                    command: RoomCommand(
                        admission: admission, number: 4, watchGeneration: 0, action: .select(mediaID: "movie-1")))
                XCTFail("Changed content under the same command ID was accepted")
            } catch RoomProtocolFailure.rejected("conflict") {}
            let stale = try await owner.execute(
                admission,
                command: RoomCommand(
                    admission: admission, number: 5, watchGeneration: 0, action: .select(mediaID: "movie-1")))
            XCTAssertEqual(stale.errorCode, "staleGeneration")
            let commands: [RoomCommand] = try [
                RoomCommand(admission: admission, number: 6, watchGeneration: 1, action: .start(mediaID: "movie-0")),
                RoomCommand(
                    admission: admission, number: 7, watchGeneration: 2,
                    action: .missing(mediaID: "movie-0", missing: true)),
                RoomCommand(admission: admission, number: 8, watchGeneration: 2, action: .end(reason: .user)),
                RoomCommand(
                    admission: admission, number: 9, watchGeneration: 3,
                    action: .meet(uri: "https://meet.google.com/abc-defg-hij")),
                RoomCommand(admission: admission, number: 10, watchGeneration: 3, action: .meet(uri: nil)),
            ]
            for command in commands {
                let result = try await owner.execute(admission, command: command)
                XCTAssertNil(result.errorCode)
            }
            let final = try await owner.snapshot(admission)
            XCTAssertEqual(final.snapshot.watchStatus, "ended")
            XCTAssertEqual(final.snapshot.watchGeneration, 3)
            XCTAssertNil(final.snapshot.meetURI)
            XCTAssertTrue(final.missingMembers.contains(admission.memberID))
            let joined = try await guest.join(
                roomID: admission.roomID, invitation: XCTUnwrap(admission.invitation),
                identity: RoomIdentity(clientRunID: "run-" + UUID().uuidString, syncplayUsername: "macOS command guest")
            )
            let guestEvents = try await guest.openEvents(joined)
            _ = try RoomBootstrap.initialEvent(await guestEvents.receive(), admission: joined)
            let forbidden = try await guest.execute(
                joined, command: RoomCommand(admission: joined, number: 1, watchGeneration: 3, action: .meet(uri: nil)))
            XCTAssertEqual(forbidden.errorCode, "forbidden")
            do {
                _ = try await guest.execute(joined, command: selection)
                XCTFail("Foreign command membership accepted")
            } catch RoomProtocolFailure.malformed {}
            try await guest.leave(joined)
            try await owner.leave(admission)
            await guest.close()
            await owner.close()
        } catch {
            await guest.close()
            await owner.close()
            throw error
        }
    }
}
