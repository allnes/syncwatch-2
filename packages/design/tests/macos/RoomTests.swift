import Testing

@testable import SyncWatchDesign

@Test func roomDraftKeepsCredentialsEphemeralAndCapabilitiesTruthful() {
    var editor = RoomEditor(values: ["username": "Alice", "creationKey": "must not restore"])
    #expect(editor.values["creationKey"] == "")
    #expect(!editor.isValid && editor.context.values["can.connectRoom"] == "false")
    editor.edit("creationKey", value: "creation-secret")
    editor.selectMode("createRoom")
    #expect(editor.values["creationKey"] == "creation-secret")
    editor.selectMode("joinRoom")
    #expect(editor.context.values["can.pasteInvitation"] == "true")
    #expect(editor.values["creationKey"] == "" && editor.values["username"] == "Alice")
    editor.edit("invitation", value: "invitation-secret")
    editor.state = "connecting"
    #expect(editor.context.values["can.pasteInvitation"] == "false")
    editor.edit("username", value: "Bob")
    editor.selectMode("createRoom")
    #expect(editor.values["username"] == "Alice" && editor.mode == "joinRoom")
    editor.clearSecrets()
    #expect(editor.values["invitation"] == "")
    editor.state = "connected"
    editor.owner = false
    #expect(editor.context.values["can.copyInvitation"] == "false")
    editor.owner = true
    #expect(editor.context.values["can.copyInvitation"] == "true")
    editor.state = "reconnecting"
    #expect(editor.busy && !editor.connected)
    #expect(editor.context.values["status"] == "reconnecting")
    #expect(editor.context.values["showForm"] == "false" && editor.context.values["can.leaveRoom"] == "true")
    #expect(
        editor.context.values["can.copyInvitation"] == "false" && editor.context.values["can.connectRoom"] == "false")
    editor.edit("username", value: "Changed")
    #expect(editor.values["username"] == "Alice")

}
