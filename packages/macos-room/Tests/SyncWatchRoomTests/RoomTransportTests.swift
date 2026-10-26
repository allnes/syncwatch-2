import Foundation
import XCTest

@testable import SyncWatchRoom

final class RoomTransportTests: XCTestCase, @unchecked Sendable {
    func testNativeRoomService() async throws {
        guard let address = ProcessInfo.processInfo.environment["SYNCWATCH_ROOM_SERVICE"],
            let key = ProcessInfo.processInfo.environment["SYNCWATCH_ROOM_CREATION_KEY"]
        else { throw XCTSkip("Requires an owned room metadata service") }
        let owner = try RoomClient(address: RoomAddress(address))
        let guest = try RoomClient(address: RoomAddress(address))
        do {
            let identity = try RoomIdentity(clientRunID: "run-" + UUID().uuidString, syncplayUsername: "macOS owner")
            let admission = try await owner.create(
                identity: identity,
                connection: RoomConnection(host: "syncplay.example.com", port: 8999, room: "Room check"),
                creationKey: RoomSecret(key))
            let events = try await owner.openEvents(admission)
            let initial = try RoomBootstrap.initialEvent(await events.receive(), admission: admission)
            XCTAssertEqual(initial.snapshot.members.count, 1)
            let joined = try await guest.join(
                roomID: admission.roomID, invitation: XCTUnwrap(admission.invitation),
                identity: RoomIdentity(clientRunID: "run-" + UUID().uuidString, syncplayUsername: "macOS guest"))
            let guestEvents = try await guest.openEvents(joined)
            let guestInitial = try RoomBootstrap.initialEvent(await guestEvents.receive(), admission: joined)
            XCTAssertEqual(guestInitial.snapshot.members.count, 2)
            let joinedEvent = try RoomWire.object(await events.receive())
            XCTAssertEqual(joinedEvent["type"] as? String, "member.bound")
            let snapshot = try await owner.snapshot(admission)
            XCTAssertEqual(snapshot.snapshot.members.count, 2)
            try await guest.leave(joined)
            let leftEvent = try RoomWire.object(await events.receive())
            XCTAssertEqual(leftEvent["type"] as? String, "member.left")
            try await owner.leave(admission)
            await guest.close()
            await owner.close()
            await owner.close()
            do {
                _ = try await owner.snapshot(admission)
                XCTFail("Closed client accepted work")
            } catch {}
        } catch {
            await guest.close()
            await owner.close()
            throw error
        }
    }
}
