import Foundation
import XCTest

@testable import SyncWatchRoom

final class RoomTransportTests: XCTestCase, @unchecked Sendable {
    func testSeededCatalogWalk() async throws {
        let environment = ProcessInfo.processInfo.environment
        guard let address = environment["SYNCWATCH_ROOM_SERVICE"], let room = environment["SYNCWATCH_CATALOG_ROOM"],
            let invitation = environment["SYNCWATCH_CATALOG_INVITATION"]
        else { throw XCTSkip("Requires an owned service with the 250-entry catalog fixture") }
        let client = try RoomClient(address: RoomAddress(address))
        do {
            let admission = try await client.join(
                roomID: room, invitation: RoomSecret(invitation),
                identity: RoomIdentity(clientRunID: "run-" + UUID().uuidString, syncplayUsername: "macOS catalog"))
            let events = try await client.openEvents(admission)
            let bootstrap = try RoomBootstrap.initialEvent(await events.receive(), admission: admission)
            var cursor: String? = bootstrap.catalogCursor
            var ids = Set<String>()
            var pages = 0
            while let current = cursor {
                guard pages < 3 else { throw RoomProtocolFailure.malformed }
                let page = try await client.catalog(admission, bootstrap: bootstrap, cursor: current)
                for entry in page.items {
                    XCTAssertNotEqual(entry.memberID, admission.memberID)
                    XCTAssertTrue(ids.insert(entry.media.mediaID).inserted)
                }
                pages += 1
                cursor = page.nextCursor
            }
            XCTAssertEqual(pages, 3)
            XCTAssertEqual(ids, Set((0..<250).map { "movie-\($0)" }))
            try await client.leave(admission)
            await client.close()
        } catch {
            await client.close()
            throw error
        }
    }
    func testDelegateCompletionReleasesAnIdleReceive() async throws {
        let delegate = RoomSessionDelegate()
        let session = URLSession(configuration: .ephemeral)
        let socket = session.webSocketTask(with: URL(string: "ws://127.0.0.1:1/events")!)
        let stream = RoomEventStream(socket: socket)
        delegate.termination.bind(stream)
        let finished = expectation(description: "Delegate releases the pending receive")
        let reader = Task {
            do {
                _ = try await stream.receive()
                XCTFail("Closed transport returned data")
            } catch RoomProtocolFailure.transport {} catch { XCTFail("Unexpected termination failure") }
            finished.fulfill()
        }
        await Task.yield()
        delegate.urlSession(session, task: socket, didCompleteWithError: URLError(.networkConnectionLost))
        delegate.urlSession(session, webSocketTask: socket, didCloseWith: .abnormalClosure, reason: nil)
        await fulfillment(of: [finished], timeout: 2)
        reader.cancel()
        await stream.close()
        await reader.value
        session.invalidateAndCancel()
    }
    func testDelegateCompletionBeforeBindingIsRetained() async throws {
        let delegate = RoomSessionDelegate()
        let session = URLSession(configuration: .ephemeral)
        let socket = session.webSocketTask(with: URL(string: "ws://127.0.0.1:1/events")!)
        let stream = RoomEventStream(socket: socket)
        delegate.urlSession(session, task: socket, didCompleteWithError: nil)
        delegate.termination.bind(stream)
        let finished = expectation(description: "Early completion reaches a later receiver")
        let reader = Task {
            do {
                _ = try await stream.receive()
                XCTFail("Ended transport returned data")
            } catch RoomProtocolFailure.transport {} catch { XCTFail("Unexpected termination failure") }
            finished.fulfill()
        }
        await fulfillment(of: [finished], timeout: 2)
        reader.cancel()
        await stream.close()
        await reader.value
        session.invalidateAndCancel()
    }
    func testCancellingIdleReceiveJoinsBeforeLeave() async throws {
        guard let address = ProcessInfo.processInfo.environment["SYNCWATCH_ROOM_SERVICE"],
            let key = ProcessInfo.processInfo.environment["SYNCWATCH_ROOM_CREATION_KEY"]
        else { throw XCTSkip("Requires an owned room metadata service") }
        let client = try RoomClient(address: RoomAddress(address))
        do {
            let identity = try RoomIdentity(
                clientRunID: "run-" + UUID().uuidString, syncplayUsername: "macOS cancellation")
            let admission = try await client.create(
                identity: identity,
                connection: RoomConnection(host: "syncplay.example.com", port: 8999, room: "Cancellation check"),
                creationKey: RoomSecret(key))
            let stream = try await client.openEvents(admission)
            _ = try RoomBootstrap.initialEvent(await stream.receive(), admission: admission)
            let pending = Task { try await stream.receive() }
            try await Task.sleep(for: .milliseconds(100))
            pending.cancel()
            do {
                _ = try await pending.value
                XCTFail("Cancelled receive returned a message")
            } catch {}
            try await client.leave(admission)
            await client.close()
            await stream.close()
        } catch {
            await client.close()
            throw error
        }
    }
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
            let empty = try await owner.catalog(admission, bootstrap: initial, cursor: initial.catalogCursor)
            XCTAssertTrue(empty.items.isEmpty)
            XCTAssertNil(empty.nextCursor)
            let refreshed = try await owner.snapshot(admission)
            do {
                _ = try await owner.catalog(admission, bootstrap: initial, cursor: initial.catalogCursor)
                XCTFail("A new bootstrap must invalidate the preceding catalog view")
            } catch RoomProtocolFailure.rejected("snapshotRequired") {}
            _ = try await owner.catalog(admission, bootstrap: refreshed, cursor: refreshed.catalogCursor)
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
