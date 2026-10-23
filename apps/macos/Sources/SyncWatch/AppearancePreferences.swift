import Foundation
import SwiftUI
import SyncWatchDesign
import SyncWatchDomain

@MainActor final class AppearancePreferences: ObservableObject {
    @Published private(set) var state = LocalState()
    private(set) var canWrite = false
    private let store: any LocalStateStore

    static var defaultURL: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("SyncWatch/local-state.json")
    }

    init(store: any LocalStateStore) {
        self.store = store
        do {
            switch try store.read() {
            case .loaded(let value):
                try value.validate()
                state = value
                canWrite = true
            case .missing, .invalid: canWrite = true
            case .unsupportedVersion: break
            }
        } catch { canWrite = false }
    }

    var editor: SettingsEditor {
        SettingsEditor(
            values: ["theme": state.preferences.theme, "language": state.preferences.language],
            editableFields: canWrite ? ["theme", "language"] : [], canSave: canWrite)
    }

    func save(_ values: [String: String]) -> Bool {
        guard canWrite, let theme = values["theme"], let language = values["language"] else { return false }
        var next = state
        next.preferences.theme = theme
        next.preferences.language = language
        do {
            try next.validate()
            try store.write(next)
            state = next
            return true
        } catch { return false }
    }

    var colorScheme: ColorScheme? {
        switch state.preferences.theme {
        case "dark": .dark
        case "light": .light
        default: nil
        }
    }
}

struct ApplicationWorkspace: View {
    @StateObject private var preferences = AppearancePreferences(
        store: FileLocalStateStore(url: AppearancePreferences.defaultURL))
    @State private var showSettings = false
    @State private var editor = SettingsEditor()

    var body: some View {
        LibraryWorkspace(
            presentation: LibraryPresentation(enabledActions: ["openSettings"]),
            language: preferences.state.preferences.language
        ) { action, _ in
            if action == "openSettings" {
                editor = preferences.editor
                showSettings = true
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsDialog(
                editor: $editor, language: preferences.state.preferences.language,
                onSave: preferences.save, onClose: { showSettings = false })
        }
        .preferredColorScheme(preferences.colorScheme)
        .environment(\.locale, Locale(identifier: preferences.state.preferences.language))
    }
}
