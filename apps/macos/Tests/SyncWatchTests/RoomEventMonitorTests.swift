import Foundation
import SyncWatchDomain
import SyncWatchRoom
import Testing

@testable import SyncWatch

@MainActor @Test(.enabled(if: ProcessInfo.processInfo.environment["SYNCWATCH_ROOM_SERVICE"] != nil))
func eventRecoveryRetainsMembershipAndCommandNumbering() async throws {
    let environment = ProcessInfo.processInfo.environment
    let address = try RoomAddress(#require(environment["SYNCWATCH_ROOM_SERVICE"]))
    let client = RoomClient(address: address)
    var monitoring: Task<Void, Error>?
    do {
        let identity = try RoomIdentity(clientRunID: "run-" + UUID().uuidString, syncplayUsername: "macOS recovery")
        let admission = try await client.create(
            identity: identity, connection: RoomConnection(host: "syncplay.example.com", port: 8999, room: "Recovery"),
            creationKey: RoomSecret(#require(environment["SYNCWATCH_ROOM_CREATION_KEY"])))
        let owner = RoomMembershipSession(client: client, admission: admission, identity: identity)
        let media = try MediaDescriptor(
            mediaID: "movie", title: "Movie", titleKey: "movie", fileSizeBytes: 10, durationMs: 60000,
            fullHashSha256: nil)
        _ = try await owner.publish([media])
        var deliveries = 0
        var recoveries = 0
        monitoring = Task {
            try await RoomEventMonitor.run(
                address: address, admission: admission, membership: owner, reconnecting: { recoveries += 1 },
                accepted: { view in
                    #expect(
                        view.bootstrap.snapshot.members.contains {
                            $0.memberID == admission.memberID && $0.identity == identity
                        })
                    deliveries += 1
                    if deliveries == 1 { throw RoomProtocolFailure.transport }
                })
        }
        let until = ContinuousClock.now + .seconds(10)
        while deliveries < 2 {
            guard ContinuousClock.now < until else { throw RoomProtocolFailure.transport }
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(recoveries == 1)
        _ = try await owner.publish([media])
        let context = try await owner.watchContext()
        let selected = try await owner.perform(.select(mediaID: media.mediaID), expected: context)
        #expect(selected.definition.selection?.media == media)
        monitoring?.cancel()
        _ = await monitoring?.result
        monitoring = nil
        var retries = 0
        do {
            try await RoomEventMonitor.run(
                address: address, admission: admission, membership: owner, reconnecting: { retries += 1 },
                accepted: { _ in throw RoomProtocolFailure.malformed })
            Issue.record("Malformed metadata was retried")
        } catch RoomProtocolFailure.malformed {}
        #expect(retries == 0)
        try await client.leave(admission)
        await client.close()
    } catch {
        monitoring?.cancel()
        _ = await monitoring?.result
        await client.close()
        throw error
    }
}
