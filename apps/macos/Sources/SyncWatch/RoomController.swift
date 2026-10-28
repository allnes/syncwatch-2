import Foundation
import SwiftUI
import SyncWatchDesign
import SyncWatchDomain
import SyncWatchLibrary
import SyncWatchRoom

struct RoomWatchMembership {
    fileprivate let owner: RoomMembershipSession
    let memberID: String
    let identity: RoomIdentity
    let epoch: String
}
struct RoomPreparedPublication {
    let lease: UUID
    let media: MediaDescriptor
}

/// The workspace owns membership independently of the visible connection sheet.
@MainActor final class RoomController: ObservableObject {
    @Published var editor = RoomEditor()
    @Published private(set) var catalogView: RoomCatalogView?
    var bootstrap: RoomBootstrap? { catalogView?.bootstrap }
    private(set) var watchBootstrap: RoomBootstrap?
    private var admission: RoomAdmission?
    private var work: Task<Void, Never>?
    private var session: RoomMembershipSession?
    private var playbackSession: RoomMembershipSession?
    private var playbackEpoch: String?
    private var catalogMap = RoomLocalCatalog()
    private var localRevision: UUID?
    private var acknowledgedRevision: UUID?
    private var localFiles: [LocalMediaFile] = []
    private var publisher: Task<Void, Never>?
    private var missingReport: Task<Void, Never>?
    private var prepared: (lease: UUID, media: MediaDescriptor)?
    private var acknowledgedPrepared: RoomPreparedPublication?
    private var stopping = false
    private var closing: Task<Void, Never>?
    var connected: Bool { editor.connected && bootstrap != nil }
    func connect() {
        guard !stopping, !editor.busy, !connected, work == nil, editor.isValid else { return }
        playbackSession = nil
        playbackEpoch = nil
        let values = editor.values
        let owner = editor.mode == "createRoom"
        editor.state = "connecting"
        editor.status = ""
        work = Task { await run(values, owner: owner) }
    }
    func libraryPresentation(_ source: LibraryPresentation, sharedStartAvailable: Bool = false) -> LibraryPresentation {
        var result = source
        if !stopping { result.enabledActions.insert("openRoom") }
        // Membership alone cannot authorize an unsynchronized local Start in a room.
        if editor.state != "disconnected" && !(connected && sharedStartAvailable) {
            result.enabledActions.remove("startWatching")
        }
        result.roomStatus =
            connected
            ? (["roomCatalogPublishing", "roomCatalogPublishFailed"].contains(editor.status)
                ? editor.status : "roomMetadataConnected")
            : editor.busy ? "roomConnecting" : editor.state == "failed" ? "roomConnectionFailed" : "disconnected"
        return result
    }
    var mediaNotice: String {
        guard connected, let bootstrap, bootstrap.snapshot.watchStatus == "active", let admission else { return "" }
        if bootstrap.missingMembers.contains(admission.memberID) || (localFiles.isEmpty && prepared == nil) {
            return "sharedWatchMediaMissing"
        }
        return bootstrap.missingMembers.isEmpty ? "" : "roomPeersMissingMedia"
    }
    private func startMissingReport() {
        guard !stopping, connected, missingReport == nil, localFiles.isEmpty, prepared == nil,
            let bootstrap, bootstrap.snapshot.watchStatus == "active", let mediaID = bootstrap.snapshot.mediaID,
            let admission, !bootstrap.missingMembers.contains(admission.memberID)
        else { return }
        let revision = localRevision
        missingReport = Task { [self] in
            defer {
                missingReport = nil
                if localRevision != revision || self.bootstrap?.snapshot.epoch != bootstrap.snapshot.epoch
                    || self.bootstrap?.snapshot.watchGeneration != bootstrap.snapshot.watchGeneration
                {
                    startMissingReport()
                }
            }
            do {
                let intent = try await beginWatch()
                try Task.checkCancellation()
                guard !stopping, localFiles.isEmpty, prepared == nil, localRevision == revision,
                    intent.context.bootstrap.snapshot.epoch == bootstrap.snapshot.epoch,
                    intent.context.bootstrap.snapshot.watchGeneration == bootstrap.snapshot.watchGeneration,
                    intent.context.bootstrap.snapshot.watchStatus == "active",
                    intent.context.bootstrap.snapshot.mediaID == mediaID
                else { return }
                _ = try await performWatch(
                    .missing(mediaID: mediaID, missing: true),
                    membership: intent.membership, expected: intent.context)
            } catch {
                // A later membership/catalog update retries under its current generation.
            }
        }
    }
    func clearSecrets() { editor.clearSecrets() }
    func pasteInvitation(_ text: String) {
        guard !stopping, !editor.busy, !editor.connected, editor.mode == "joinRoom" else { return }
        var next = editor
        do {
            let invitation = try RoomInvitation.parse(text)
            next.edit("roomID", value: invitation.roomID)
            next.edit("invitation", value: invitation.credential.copyInvitation())
        } catch {
            next.clearSecrets()
            next.edit("roomID", value: "")
            next.status = "roomInvitationInvalid"
        }
        editor = next
    }
    func invitationToCopy() -> String? {
        guard connected, let admission, let invitation = admission.invitation else { return nil }
        return try? RoomInvitation(roomID: admission.roomID, credential: invitation).copyText()
    }
    func invitationCopyCompleted(_ copied: Bool) {
        guard connected else { return }
        editor.status = copied ? "roomInvitationCopied" : "roomInvitationCopyFailed"
    }
    func close() async {
        if let closing {
            await closing.value
            return
        }
        let task = Task { await stop() }
        closing = task
        await task.value
        closing = nil
    }
    private func stop() async {
        if stopping {
            if let work { await work.value }
            return
        }
        stopping = true
        playbackSession = nil
        playbackEpoch = nil
        work?.cancel()
        publisher?.cancel()
        if let work { await work.value }
        self.work = nil
        stopping = false
        catalogView = nil
        admission = nil
        editor.state = "disconnected"
        editor.status = ""
        editor.roomID = ""
        editor.memberCount = 0
        editor.owner = false
        editor.clearSecrets()
    }
    func updateLibrary(revision: UUID, files: [LocalMediaFile]) {
        guard localRevision != revision else { return }
        localRevision = revision
        localFiles = files
        startPublisher()
        startMissingReport()
    }
    func isCurrent(_ membership: RoomWatchMembership) -> Bool {
        !stopping && connected && session === membership.owner && admission?.memberID == membership.memberID
            && admission?.bootstrap.snapshot.epoch == membership.epoch
    }
    // An admitted native scope survives metadata transport loss. New starts still require isCurrent.
    func canContinuePlayback(_ membership: RoomWatchMembership) -> Bool {
        !stopping && playbackSession === membership.owner && playbackEpoch == membership.epoch
    }
    static func isMetadataInterruption(_ error: any Error) -> Bool {
        if error is URLError { return true }
        switch error {
        case RoomProtocolFailure.transport, RoomProtocolFailure.closed,
            RoomProtocolFailure.rejected("transport"):
            return true
        default: return false
        }
    }
    func beginWatch() async throws -> (membership: RoomWatchMembership, context: RoomWatchContext) {
        guard let session, let admission,
            let member = admission.bootstrap.snapshot.members.first(where: { $0.memberID == admission.memberID })
        else { throw RoomProtocolFailure.closed }
        let membership = RoomWatchMembership(
            owner: session, memberID: admission.memberID,
            identity: member.identity, epoch: admission.bootstrap.snapshot.epoch)
        return (membership, try await watchContext(membership))
    }
    func watchContext(_ membership: RoomWatchMembership) async throws -> RoomWatchContext {
        guard isCurrent(membership) else { throw RoomProtocolFailure.closed }
        let value = try await membership.owner.watchContext()
        try Task.checkCancellation()
        guard isCurrent(membership) else { throw RoomProtocolFailure.closed }
        recordWatch(value.bootstrap)
        return value
    }
    func performWatch(_ action: RoomCommandAction, membership: RoomWatchMembership, expected: RoomWatchContext)
        async throws -> RoomWatchContext
    {
        guard isCurrent(membership) else { throw RoomProtocolFailure.closed }
        let value = try await membership.owner.perform(action, expected: expected)
        try Task.checkCancellation()
        guard isCurrent(membership) else { throw RoomProtocolFailure.closed }
        recordWatch(value.bootstrap)
        return value
    }
    func publishPrepared(_ media: MediaDescriptor, membership: RoomWatchMembership) async throws
        -> RoomPreparedPublication
    {
        guard isCurrent(membership), media.fullHashSha256 != nil, (media.durationMs ?? 0) > 0 else {
            throw RoomProtocolFailure.malformed
        }
        let lease = UUID()
        prepared = (lease, media)
        localRevision = UUID()
        startPublisher()
        do {
            while true {
                try Task.checkCancellation()
                guard isCurrent(membership), prepared?.lease == lease else { throw RoomProtocolFailure.closed }
                if let acknowledgedPrepared, acknowledgedPrepared.lease == lease { return acknowledgedPrepared }
                guard let publisher else { throw RoomProtocolFailure.rejected("unavailable") }
                await publisher.value
            }
        } catch {
            clearPrepared(lease, membership: membership)
            throw error
        }
    }
    func clearPrepared(_ lease: UUID, membership: RoomWatchMembership) {
        guard isCurrent(membership), prepared?.lease == lease else { return }
        prepared = nil
        localRevision = UUID()
        startPublisher()
    }
    private func startPublisher() {
        guard !stopping, connected, publisher == nil, let session, localRevision != nil,
            localRevision != acknowledgedRevision
        else { return }
        publisher = Task { await publishLibrary(session) }
    }
    private func publishLibrary(_ owner: RoomMembershipSession) async {
        defer { publisher = nil }
        while !Task.isCancelled, !stopping, session === owner, let revision = localRevision,
            revision != acknowledgedRevision
        {
            do {
                let loaded = prepared
                let publication = try catalogMap.prepare(localFiles, prepared: loaded?.media)
                editor.status = "roomCatalogPublishing"
                let view = try await owner.publish(publication.items)
                try Task.checkCancellation()
                guard !stopping, session === owner else { return }
                catalogMap.acknowledge(publication)
                acknowledgedPrepared = loaded.flatMap { loaded in
                    publication.items.first { $0.mediaID == publication.localIDs[loaded.media.mediaID] }
                        .map { RoomPreparedPublication(lease: loaded.lease, media: $0) }
                }
                acknowledgedRevision = revision
                accept(view)
                if ["roomCatalogPublishing", "roomCatalogPublishFailed"].contains(editor.status) { editor.status = "" }
            } catch {
                guard !Task.isCancelled, !stopping, session === owner else { return }
                if localRevision != revision { continue }
                editor.status = "roomCatalogPublishFailed"
                return
            }
        }
    }
    private func accept(_ view: RoomCatalogView) {
        recordWatch(view.bootstrap)
        guard view.bootstrap.snapshot.sequence >= (bootstrap?.snapshot.sequence ?? 0) else { return }
        catalogView = view
        editor.memberCount = view.bootstrap.snapshot.members.count
        startMissingReport()
    }
    private func recordWatch(_ bootstrap: RoomBootstrap) {
        if bootstrap.snapshot.sequence >= (watchBootstrap?.snapshot.sequence ?? 0) { watchBootstrap = bootstrap }
    }
    private func run(_ values: [String: String], owner: Bool) async {
        var current: RoomClient?
        var admitted: RoomAdmission?
        var failed = false
        var interrupted = false
        do {
            let next = try RoomClient(address: RoomAddress(values["serviceAddress"] ?? ""))
            current = next
            let identity = try RoomIdentity(
                clientRunID: "run-" + UUID().uuidString, syncplayUsername: values["username"] ?? "")
            let value: RoomAdmission
            if owner {
                guard let port = Int(values["syncplayPort"] ?? "") else { throw RoomProtocolFailure.malformed }
                value = try await next.create(
                    identity: identity,
                    connection: RoomConnection(
                        host: values["syncplayHost"] ?? "", port: port, room: values["roomName"] ?? ""),
                    creationKey: RoomSecret(values["creationKey"] ?? ""))
            } else {
                value = try await next.join(
                    roomID: values["roomID"] ?? "", invitation: RoomSecret(values["invitation"] ?? ""),
                    identity: identity)
            }
            admitted = value
            admission = value
            editor.clearSecrets()
            let stream = try await next.openEvents(value)
            let initial = try await withThrowingTaskGroup(of: RoomBootstrap.self) { group in
                group.addTask { try RoomBootstrap.initialEvent(await stream.receive(), admission: value) }
                group.addTask {
                    try await Task.sleep(for: .seconds(20))
                    throw RoomProtocolFailure.transport
                }
                defer { group.cancelAll() }
                return try await group.next()!
            }
            try Task.checkCancellation()
            let ownerSession = RoomMembershipSession(client: next, admission: value, identity: identity)
            let firstView = try await ownerSession.refresh(initial: initial)
            try Task.checkCancellation()
            catalogMap = RoomLocalCatalog()
            prepared = nil
            acknowledgedPrepared = nil
            acknowledgedRevision = nil
            session = ownerSession
            playbackSession = ownerSession
            playbackEpoch = value.bootstrap.snapshot.epoch
            catalogView = firstView
            watchBootstrap = firstView.bootstrap
            editor.state = "connected"
            editor.roomID = value.roomID
            editor.memberCount = initial.snapshot.members.count
            editor.owner = owner
            startPublisher()
            startMissingReport()
            while !Task.isCancelled {
                let event = try RoomInvalidation.decode(await stream.receive())
                guard let previous = bootstrap, event.epoch == previous.snapshot.epoch else {
                    throw RoomProtocolFailure.malformed
                }
                if event.sequence <= previous.snapshot.sequence { continue }
                let complete = try await ownerSession.refresh(sequence: event.sequence)
                try Task.checkCancellation()
                accept(complete)
            }
        } catch {
            failed = !Task.isCancelled
            interrupted = failed && Self.isMetadataInterruption(error) && playbackSession != nil
            if !interrupted {
                playbackSession = nil
                playbackEpoch = nil
            }
            editor.state = "connecting"
        }
        missingReport?.cancel()
        await missingReport?.value
        missingReport = nil
        publisher?.cancel()
        await publisher?.value
        publisher = nil
        session = nil
        watchBootstrap = nil
        acknowledgedRevision = nil
        catalogMap = RoomLocalCatalog()
        prepared = nil
        acknowledgedPrepared = nil
        if let current {
            // Cleanup work is owned and bounded even when the attempt's caller was cancelled.
            if let admitted, !interrupted {
                let leaving = Task { try? await current.leave(admitted) }
                let deadline = Task {
                    try? await Task.sleep(for: .seconds(3))
                    leaving.cancel()
                }
                await leaving.value
                deadline.cancel()
                await deadline.value
            }
            await current.close()
        }
        admission = nil
        catalogView = nil
        editor.clearSecrets()
        editor.memberCount = 0
        editor.owner = false
        work = nil
        if failed {
            editor.state = "failed"
            editor.status = "roomConnectionFailed"
        }
    }
}
