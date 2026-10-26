import SwiftUI

/// Memory-only connection draft. This model never persists credentials.
public struct RoomEditor: Sendable {
    public private(set) var values = SyncWatchRoomForm.defaults
    public private(set) var mode = "createRoom"
    public var state = "disconnected"
    public var status = ""
    public var roomID = ""
    public var memberCount = 0
    public var owner = false
    public init(values: [String: String] = [:]) {
        for field in SyncWatchRoomForm.fields where field.kind != "secret" {
            if let value = values[field.id] { self.values[field.id] = value }
        }
    }
    public var busy: Bool { state == "connecting" }
    public var connected: Bool { state == "connected" }
    public var fields: [SyncWatchRoomFormField] {
        SyncWatchRoomForm.fields.filter { $0.section == "connection" || $0.section == mode }
    }
    public var isValid: Bool {
        fields.allSatisfy {
            guard let value = values[$0.id], !value.isEmpty, value.utf16.count <= $0.maxLength,
                !value.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 })
            else { return false }
            return true
        }
    }
    public mutating func edit(_ id: String, value: String) {
        guard !busy, !connected, let field = fields.first(where: { $0.id == id }), value.utf16.count <= field.maxLength
        else { return }
        values[id] = value
        status = ""
    }
    public mutating func selectMode(_ mode: String) {
        guard !busy, !connected, self.mode != mode, ["createRoom", "joinRoom"].contains(mode) else { return }
        clearSecrets()
        self.mode = mode
        status = ""
    }
    public mutating func clearSecrets() {
        for field in SyncWatchRoomForm.fields where field.kind == "secret" { values[field.id] = "" }
    }
    public var context: DesignContext {
        let rows = fields.map {
            DesignContext([
                "id": $0.id, "label": $0.label, "value": values[$0.id] ?? "", "secret": String($0.kind == "secret"),
                "editable": String(!busy),
            ])
        }
        return DesignContext(
            [
                "namespace": "room", "showForm": String(!connected), "connected": String(connected),
                "createMode": String(mode == "createRoom"), "joinMode": String(mode == "joinRoom"),
                "connectLabel": mode,
                "status": busy ? "roomConnecting" : status, "roomID": roomID, "memberCount": String(memberCount),
                "can.close": "true", "can.chooseRoomMode": String(!busy && !connected),
                "can.connectRoom": String(!busy && !connected && isValid), "can.leaveRoom": String(connected),
                "can.copyInvitation": String(connected && owner),
            ], collections: ["fields": rows])
    }
}
public struct RoomDialog: View {
    @Binding private var editor: RoomEditor
    public var language: String
    public var onAction: (String) -> Void
    public init(editor: Binding<RoomEditor>, language: String = "en", onAction: @escaping (String) -> Void = { _ in }) {
        _editor = editor
        self.language = language
        self.onAction = onAction
    }
    public var body: some View {
        DesignSurface("Room", context: editor.context, language: language) { event in
            switch event.action {
            case "editRoomField": if let id = event.payload, let value = event.value { editor.edit(id, value: value) }
            case "chooseRoomMode": if let mode = event.payload { editor.selectMode(mode) }
            default: onAction(event.action)
            }
        }
    }
}
