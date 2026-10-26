import Foundation
import SwiftUI
import SyncWatchDesign
import SyncWatchRoom

/// The workspace owns membership independently of the visible connection sheet.
@MainActor final class RoomController: ObservableObject {
    @Published var editor = RoomEditor()
    @Published private(set) var bootstrap: RoomBootstrap?
    private var admission: RoomAdmission?
    private var work: Task<Void, Never>?
    private var stopping = false
    private var closing: Task<Void, Never>?
    var connected: Bool { editor.connected && bootstrap != nil }
    func connect() {
        guard !stopping, !editor.busy, !connected, work == nil, editor.isValid else { return }
        let values = editor.values
        let owner = editor.mode == "createRoom"
        editor.state = "connecting"
        editor.status = ""
        work = Task { await run(values, owner: owner) }
    }
    func libraryPresentation(_ source: LibraryPresentation) -> LibraryPresentation {
        var result = source
        if !stopping { result.enabledActions.insert("openRoom") }
        // Membership alone cannot authorize an unsynchronized local Start in a room.
        if editor.state != "disconnected" { result.enabledActions.remove("startWatching") }
        result.roomStatus =
            connected
            ? "roomMetadataConnected"
            : editor.busy ? "roomConnecting" : editor.state == "failed" ? "roomConnectionFailed" : "disconnected"
        return result
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
    func invitationCopied() { editor.status = "roomInvitationCopied" }
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
        work?.cancel()
        if let work { await work.value }
        self.work = nil
        stopping = false
        bootstrap = nil
        admission = nil
        editor.state = "disconnected"
        editor.status = ""
        editor.roomID = ""
        editor.memberCount = 0
        editor.owner = false
        editor.clearSecrets()
    }
    private func run(_ values: [String: String], owner: Bool) async {
        var current: RoomClient?
        var admitted: RoomAdmission?
        var failed = false
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
            bootstrap = initial
            editor.state = "connected"
            editor.roomID = value.roomID
            editor.memberCount = initial.snapshot.members.count
            editor.owner = owner
            while !Task.isCancelled {
                let event = try RoomInvalidation.decode(await stream.receive())
                guard let previous = bootstrap, event.epoch == previous.snapshot.epoch else {
                    throw RoomProtocolFailure.malformed
                }
                if event.sequence <= previous.snapshot.sequence { continue }
                let snapshot = try await next.snapshot(value)
                guard snapshot.snapshot.epoch == previous.snapshot.epoch, snapshot.snapshot.sequence >= event.sequence,
                    snapshot.connection == initial.connection,
                    snapshot.snapshot.members.contains(where: {
                        $0.memberID == value.memberID && $0.identity == identity
                    })
                else { throw RoomProtocolFailure.malformed }
                bootstrap = snapshot
                editor.memberCount = snapshot.snapshot.members.count
            }
        } catch {
            failed = !Task.isCancelled
            editor.state = "connecting"
        }
        if let current {
            // Cleanup work is owned and bounded even when the attempt's caller was cancelled.
            if let admitted {
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
        bootstrap = nil
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
