import Foundation
import SyncWatchDesign
import SyncWatchPlayback
import SyncWatchRoom
import Testing

@testable import SyncWatch

@MainActor @Test func invitationPasteIsAtomicAndKeepsTheServiceExplicit() {
    let controller = RoomController()
    controller.editor.selectMode("joinRoom")
    controller.editor.edit("serviceAddress", value: "https://rooms.example.com")
    controller.editor.edit("username", value: "Peer")
    let credential = String(repeating: "A", count: 64)
    controller.pasteInvitation("room-paste\r\n" + credential)
    #expect(controller.editor.values["roomID"] == "room-paste")
    #expect(controller.editor.values["invitation"] == credential && controller.editor.isValid)
    #expect(controller.editor.values["serviceAddress"] == "https://rooms.example.com")
    controller.editor.state = "connecting"
    controller.pasteInvitation("invalid")
    #expect(controller.editor.values["invitation"] == credential)
    controller.editor.state = "disconnected"
    controller.pasteInvitation("invalid")
    #expect(controller.editor.values["invitation"] == "" && controller.editor.values["roomID"] == "")
    #expect(!controller.editor.isValid && controller.editor.status == "roomInvitationInvalid")
    #expect(controller.editor.values["username"] == "Peer")
}

@MainActor @Test func roomAttemptRequiresExplicitExitBeforeLocalPlayback() async {
    let controller = RoomController()
    let source = LibraryPresentation.gallery(.selected)
    #expect(source.allows("startWatching"))
    for state in ["connecting", "connected", "failed"] {
        controller.editor.state = state
        #expect(!controller.libraryPresentation(source).allows("startWatching"))
        if state == "failed" { #expect(controller.editor.context.values["can.leaveRoom"] == "true") }
        await controller.close()
        #expect(controller.libraryPresentation(source).allows("startWatching"))
    }
}

@MainActor @Test(.enabled(if: ProcessInfo.processInfo.environment["SYNCWATCH_ROOM_SERVICE"] != nil))
func connectedRoomClosesAndCanConnectAgain() async throws {
    let environment = ProcessInfo.processInfo.environment
    let address = try #require(environment["SYNCWATCH_ROOM_SERVICE"])
    let key = try #require(environment["SYNCWATCH_ROOM_CREATION_KEY"])
    let controller = RoomController()
    let runtime = VLCPlaybackRuntime()
    if let package = environment["SYNCWATCH_ROOM_MEDIA_PACKAGE"] {
        try await runtime.open(package: URL(filePath: package))
    }
    var activeGuest: RoomClient?
    do {
        for iteration in 0..<2 {
            for (field, value) in [
                "serviceAddress": address, "username": "macOS workspace", "creationKey": key,
                "syncplayHost": "syncplay.example.com", "roomName": "Workspace lifecycle",
            ] { controller.editor.edit(field, value: value) }
            controller.connect()
            let deadline = ContinuousClock.now + .seconds(20)
            while controller.editor.busy && ContinuousClock.now < deadline {
                try await Task.sleep(for: .milliseconds(20))
            }
            #expect(controller.connected)
            if iteration == 0, let delay = environment["SYNCWATCH_ROOM_IDLE_TEST_SECONDS"], let seconds = Int(delay) {
                try await Task.sleep(for: .seconds(seconds))
            }
            let invitation = try #require(controller.invitationToCopy()?.split(separator: "\n").map(String.init))
            let guest = try RoomClient(address: RoomAddress(address))
            activeGuest = guest
            let admission = try await guest.join(
                roomID: invitation[0], invitation: RoomSecret(invitation[1]),
                identity: RoomIdentity(clientRunID: "run-" + UUID().uuidString, syncplayUsername: "macOS peer"))
            let updateDeadline = ContinuousClock.now + .seconds(5)
            while controller.editor.memberCount != 2 && ContinuousClock.now < updateDeadline {
                try await Task.sleep(for: .milliseconds(20))
            }
            #expect(controller.editor.memberCount == 2)
            try await guest.leave(admission)
            await guest.close()
            activeGuest = nil
            await controller.close()
            #expect(!controller.connected && !controller.editor.busy)
            #expect(controller.editor.memberCount == 0)
            #expect(controller.invitationToCopy() == nil)
            await controller.close()
        }
    } catch {
        await activeGuest?.close()
        await controller.close()
        await runtime.close()
        throw error
    }
    await runtime.close()
}
