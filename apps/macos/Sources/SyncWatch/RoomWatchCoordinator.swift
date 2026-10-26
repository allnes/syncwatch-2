import Foundation
import SwiftUI
import SyncWatchBridge
import SyncWatchDesign
import SyncWatchDomain
import SyncWatchRoom

/// Joins metadata admission, the loaded native input and the helper without transferring native ownership.
@MainActor final class RoomWatchCoordinator: ObservableObject {
    @Published private(set) var busy = false
    @Published private(set) var status = ""
    @Published var errorKey: String?
    private let room: RoomController
    private let watch: WatchSessionCoordinator
    private let helper: HelperConfiguration
    private var work: Task<Void, Never>?
    private var active: (membership: RoomWatchMembership, context: RoomWatchContext, player: PlaybackController)?
    private var seenMembership = false
    private var closing = false
    private var admitted = false

    init(room: RoomController, watch: WatchSessionCoordinator, helper: HelperConfiguration) {
        self.room = room
        self.watch = watch
        self.helper = helper
    }
    func libraryPresentation(_ source: LibraryPresentation) -> LibraryPresentation {
        var result = room.libraryPresentation(source, sharedStartAvailable: !busy && active == nil)
        if room.connected, !busy, active == nil, watch.runtimeAvailable, source.selectedID != nil {
            result.enabledActions.insert("startWatching")
        }
        if busy || closing { result.enabledActions.remove("startWatching") }
        if !status.isEmpty { result.roomStatus = status }
        return result
    }
    func membershipChanged() {
        if !room.connected {
            seenMembership = false
            return
        }
        guard !seenMembership else { return }
        seenMembership = true
        // Joining metadata cannot leave a previously local player authorized to play.
        if work == nil, let player = watch.player {
            player.requireSharedAdmission()
            busy = true
            work = Task { [self] in
                await player.revokeShared()
                busy = false
                work = nil
            }
        }
    }
    func start(_ selection: LibraryMediaSelection) {
        guard !closing, work == nil else { return }
        if room.editor.state == "disconnected" {
            watch.start(selection)
            return
        }
        guard room.connected, watch.runtimeAvailable else { return }
        busy = true
        errorKey = nil
        status = "sharedWatchPreparing"
        work = Task { [self] in await run(selection) }
    }
    private func run(_ selection: LibraryMediaSelection) async {
        var publication: RoomPreparedPublication?
        var membership: RoomWatchMembership?
        var owned: PlaybackController?
        var finished = false
        admitted = false
        do {
            let intent = try await room.beginWatch()
            membership = intent.membership
            let runtime = try await helper.verify()
            try Task.checkCancellation()
            // A fresh scope prevents a prepared hash or helper from being reused for another load.
            watch.end()
            watch.start(selection, requiresSharedAdmission: true)
            let scope = watch.scope
            let deadline = ContinuousClock.now + .seconds(20)
            while owned == nil {
                try Task.checkCancellation()
                guard room.isCurrent(intent.membership), watch.scope == scope, watch.errorKey == nil,
                    ContinuousClock.now < deadline
                else { throw HelperSessionFailure.unavailable }
                if let player = watch.player, player.scope == scope, !player.failed,
                    let actual = try? await player.player.observe(scope), actual.status == .ready,
                    actual.seekable, (actual.durationMs ?? 0) > 0
                {
                    owned = player
                } else {
                    try await Task.sleep(for: .milliseconds(100))
                }
            }
            guard let player = owned else { throw HelperSessionFailure.unavailable }
            let local = try await player.prepareSharedMedia()
            publication = try await room.publishPrepared(local, membership: intent.membership)
            var context = try await room.watchContext(intent.membership)
            try Self.requireSameGeneration(intent.context, context)
            if context.bootstrap.snapshot.watchStatus != "active" {
                guard let publication else { throw HelperSessionFailure.unavailable }
                context = try await room.performWatch(
                    .select(mediaID: publication.media.mediaID), membership: intent.membership, expected: context)
                guard context.definition.selection?.media == publication.media else {
                    throw HelperSessionFailure.malformed
                }
                context = try await room.performWatch(
                    .start(mediaID: publication.media.mediaID), membership: intent.membership, expected: context)
            }
            try Self.requireMatch(local, context)
            let current = try await room.watchContext(intent.membership)
            try Self.requireSameGeneration(context, current)
            try Self.requireMatch(local, current)
            guard watch.player === player, watch.scope == scope else { throw HelperSessionFailure.unavailable }
            active = (intent.membership, current, player)
            let transport = try await HelperProcess.launch(executable: runtime.executable, runtime: runtime.package)
            do {
                try Task.checkCancellation()
                guard authorized() else { throw HelperSessionFailure.unavailable }
                let connection = current.bootstrap.connection
                let remote = current.definition.selection!.media
                try await player.connectShared(
                    transport: transport,
                    endpoint: SyncplayEndpoint(
                        host: connection.host, port: connection.port, room: connection.room,
                        username: intent.membership.identity.syncplayUsername),
                    media: SharedMedia(
                        handle: "loaded-" + UUID().uuidString, name: remote.title,
                        durationMs: local.durationMs!, fileSizeBytes: UInt64(local.fileSizeBytes)),
                    revision: runtime.revision, requireDeclaredIdentity: true,
                    authority: { [weak self] in self?.authorized() == true })
            } catch {
                await transport.close()
                throw error
            }
            let readyDeadline = ContinuousClock.now + .seconds(20)
            while true {
                try Task.checkCancellation()
                let actual = try await player.player.observe(scope)
                if actual.ended {
                    finished = true
                    status = "ended"
                    break
                }
                guard authorized(), !player.failed else { throw HelperSessionFailure.unavailable }
                guard player.sharedState?.connection != .failed, player.sharedState?.connection != .stopped else {
                    throw HelperSessionFailure.unavailable
                }
                if player.sharedState?.connection == .connected && player.sharedState?.ready == true {
                    guard player.sharedState?.acceptedUsername == intent.membership.identity.syncplayUsername else {
                        throw HelperSessionFailure.malformed
                    }
                    admitted = true
                    if busy {
                        busy = false
                        status = "sharedWatchConnected"
                    }
                } else if !admitted, ContinuousClock.now >= readyDeadline {
                    throw HelperSessionFailure.timeout
                }
                try await Task.sleep(for: .milliseconds(100))
            }
        } catch is CancellationError {
        } catch {
            let key = owned?.sharedState?.identityRejected == true ? "sharedWatchIdentityRejected" : "sharedWatchFailed"
            errorKey = key
            status = key
        }
        let previous = active
        active = nil
        admitted = false
        await owned?.revokeShared()
        if finished, let previous, room.editor.owner, room.isCurrent(previous.membership) {
            // Completion releases only this helper; bookkeeping cannot control a peer's movie.
            _ = try? await room.performWatch(
                .end(reason: .finished), membership: previous.membership, expected: previous.context)
        }
        if let publication, let membership { room.clearPrepared(publication.lease, membership: membership) }
        busy = false
        work = nil
    }
    private func authorized() -> Bool {
        guard !closing, let active, watch.player === active.player, watch.scope == active.player.scope else {
            return false
        }
        // Metadata generations authorize a new load; Syncplay owns an already admitted file's timing.
        if admitted { return room.canContinuePlayback(active.membership) }
        guard room.isCurrent(active.membership), let current = room.watchBootstrap else { return false }
        return current.snapshot.epoch == active.context.bootstrap.snapshot.epoch
            && current.snapshot.watchGeneration == active.context.bootstrap.snapshot.watchGeneration
            && current.snapshot.watchStatus == "active"
    }
    static func requireSameGeneration(_ expected: RoomWatchContext, _ current: RoomWatchContext) throws {
        guard expected.bootstrap.snapshot.epoch == current.bootstrap.snapshot.epoch,
            expected.bootstrap.snapshot.watchGeneration == current.bootstrap.snapshot.watchGeneration
        else { throw RoomProtocolFailure.rejected("staleGeneration") }
    }
    static func requireMatch(_ local: MediaDescriptor, _ context: RoomWatchContext) throws {
        guard context.bootstrap.snapshot.watchStatus == "active", let selected = context.definition.selection,
            try MediaAgreement.resolve(selected.media, local: [local]).status == .matched
        else {
            throw HelperSessionFailure.unavailable
        }
    }
    func end() async {
        let previous = active
        await stop()
        if let previous, room.editor.owner, room.isCurrent(previous.membership) {
            do {
                _ = try await room.performWatch(
                    .end(reason: .user), membership: previous.membership, expected: previous.context)
            } catch { /* Local End succeeded; metadata bookkeeping is best effort. */  }
        }
        watch.end()
        status = ""
    }
    func leave() async {
        await stop()
        await room.close()
        await watch.player?.revokeShared(releaseAdmission: true)
        status = ""
        seenMembership = false
    }
    private func stop() async {
        work?.cancel()
        await work?.value
    }
    func close() async {
        closing = true
        await stop()
    }
}
