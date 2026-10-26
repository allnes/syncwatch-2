import Foundation
import XCTest

@testable import SyncWatchRoom

final class RoomTransportTests: XCTestCase, @unchecked Sendable {
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
