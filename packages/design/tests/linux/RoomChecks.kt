package syncwatch.design.tests

import syncwatch.design.RoomEditor

fun roomChecks() {
    var editor = RoomEditor(mapOf("username" to "Alice", "creationKey" to "must not restore"))
    check(editor.values["creationKey"] == "" && !editor.isValid && editor.context.values["can.connectRoom"] == "false")
    editor = editor.edit("creationKey", "creation-secret").selectMode("createRoom"); check(editor.values["creationKey"] == "creation-secret")
    editor = editor.selectMode("joinRoom"); check(editor.values["creationKey"] == "" && editor.values["username"] == "Alice")
    editor = editor.edit("invitation", "invitation-secret").copy(state = "connecting")
    editor = editor.edit("username", "Bob").selectMode("createRoom"); check(editor.values["username"] == "Alice" && editor.mode == "joinRoom")
    editor = editor.clearSecrets(); check(editor.values["invitation"] == "")
    editor = editor.copy(state = "connected", owner = false); check(editor.context.values["can.copyInvitation"] == "false")
    editor = editor.copy(owner = true); check(editor.context.values["can.copyInvitation"] == "true")
}
