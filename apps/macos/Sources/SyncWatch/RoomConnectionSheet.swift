import AppKit
import SwiftUI
import SyncWatchDesign

/// Observe membership inside the presentation host as well as the owning workspace.
@MainActor struct RoomConnectionSheet: View {
    @ObservedObject var room: RoomController
    var language: String
    var dismiss: () -> Void

    var body: some View {
        RoomDialog(editor: $room.editor, language: language, onAction: action)
            .interactiveDismissDisabled(room.editor.busy)
    }
    private func action(_ action: String) {
        switch action {
        case "connectRoom": room.connect()
        case "leaveRoom": Task { await room.close() }
        case "pasteInvitation": room.pasteInvitation(NSPasteboard.general.string(forType: .string) ?? "")
        case "copyInvitation":
            if let invitation = room.invitationToCopy() {
                NSPasteboard.general.clearContents()
                room.invitationCopyCompleted(NSPasteboard.general.setString(invitation, forType: .string))
            }
        case "close":
            if room.editor.busy {
                Task {
                    await room.close()
                    dismiss()
                }
            } else {
                room.clearSecrets()
                dismiss()
            }
        default: break
        }
    }
}
