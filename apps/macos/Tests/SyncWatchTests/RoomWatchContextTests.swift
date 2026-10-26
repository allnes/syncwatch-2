import Foundation
import SyncWatchDomain
import SyncWatchRoom
import Testing

@testable import SyncWatch

@MainActor @Test(.enabled(if: ProcessInfo.processInfo.environment["SYNCWATCH_ROOM_SERVICE"] != nil))
func watchIntentUsesTheMembershipCounterAndFrozenEdition() async throws {
    let environment = ProcessInfo.processInfo.environment
    let address = try RoomAddress(#require(environment["SYNCWATCH_ROOM_SERVICE"]))
    let client = RoomClient(address: address)
    let peer = RoomClient(address: address)
    do {
        let identity = try RoomIdentity(clientRunID: "run-" + UUID().uuidString, syncplayUsername: "macOS watch")
        let admission = try await client.create(
            identity: identity,
            connection: RoomConnection(host: "syncplay.example.com", port: 8999, room: "Watch context"),
            creationKey: RoomSecret(#require(environment["SYNCWATCH_ROOM_CREATION_KEY"])))
        let stream = try await client.openEvents(admission)
        _ = try RoomBootstrap.initialEvent(await stream.receive(), admission: admission)
        let owner = RoomMembershipSession(client: client, admission: admission, identity: identity)
        let descriptor = try MediaDescriptor(
            mediaID: "movie-a", title: "Movie", titleKey: "movie", fileSizeBytes: 1000,
            durationMs: 60000, fullHashSha256: String(repeating: "a", count: 64))
        _ = try await owner.publish([descriptor])
        let idle = try await owner.watchContext()
        #expect(idle.definition.selection == nil)
        let selected = try await owner.perform(.select(mediaID: "movie-a"), expected: idle)
        #expect(selected.definition.selection?.media == descriptor)
        _ = try await owner.publish([])
        #expect(try await owner.watchContext().definition.selection?.media == descriptor)
        let peerIdentity = try RoomIdentity(clientRunID: "run-" + UUID().uuidString, syncplayUsername: "macOS peer")
        let joined = try await peer.join(
            roomID: admission.roomID, invitation: #require(admission.invitation), identity: peerIdentity)
        let peerStream = try await peer.openEvents(joined)
        _ = try RoomBootstrap.initialEvent(await peerStream.receive(), admission: joined)
        let peerOwner = RoomMembershipSession(client: peer, admission: joined, identity: peerIdentity)
        _ = try await peerOwner.publish([descriptor])
        _ = try await peerOwner.perform(.select(mediaID: "movie-a"), expected: peerOwner.watchContext())
        do {
            _ = try await owner.perform(.start(mediaID: "movie-a"), expected: selected)
            Issue.record("A stale user intent overwrote the peer's generation")
        } catch RoomProtocolFailure.rejected("staleGeneration") {}
        let current = try await owner.watchContext()
        let active = try await owner.perform(.start(mediaID: "movie-a"), expected: current)
        #expect(active.bootstrap.snapshot.watchStatus == "active")
        #expect(active.definition.selection?.memberID == joined.memberID)
        _ = try await owner.perform(.end(reason: .user), expected: active)
        try await peer.leave(joined)
        try await client.leave(admission)
        await peer.close()
        await client.close()
    } catch {
        await peer.close()
        await client.close()
        throw error
    }
}
