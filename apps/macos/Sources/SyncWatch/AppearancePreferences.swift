import AppKit
import Foundation
import SwiftUI
import SyncWatchDesign
import SyncWatchDomain
import SyncWatchLibrary

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

@MainActor struct ApplicationWorkspace: View {
    @StateObject private var preferences: AppearancePreferences
    @StateObject private var library: LibraryController
    init() {
        let preferences = AppearancePreferences(store: FileLocalStateStore(url: AppearancePreferences.defaultURL))
        _preferences = StateObject(wrappedValue: preferences)
        _library = StateObject(
            wrappedValue: LibraryController(
                store: FileLibraryAccessStore(
                    url: AppearancePreferences.defaultURL.deletingLastPathComponent().appendingPathComponent(
                        "library-access.json")),
                selectedID: preferences.state.selectedMediaID))
    }
    @State private var showSettings = false
    @State private var editor = SettingsEditor()

    var body: some View {
        LibraryWorkspace(
            presentation: library.presentation,
            language: preferences.state.preferences.language
        ) { action, value in
            if action == "chooseFolder" {
                chooseFolder()
            } else if action == "rescan" {
                library.rescan()
            } else if action == "selectMovie", let value {
                library.select(value)
            } else if action == "openSettings" {
                editor = preferences.editor
                showSettings = true
            }
        }
        .task { library.restore() }
        .onDisappear { library.close() }
        .alert(
            SyncWatchCopy.text("brand", language: preferences.state.preferences.language),
            isPresented: Binding(get: { library.errorKey != nil }, set: { if !$0 { library.errorKey = nil } })
        ) {
            Button(SyncWatchCopy.text("close", language: preferences.state.preferences.language)) {
                library.errorKey = nil
            }
        } message: {
            Text(
                SyncWatchCopy.text(
                    library.errorKey ?? "libraryUnavailable", language: preferences.state.preferences.language))
        }
        .sheet(isPresented: $showSettings) {
            SettingsDialog(
                editor: $editor, language: preferences.state.preferences.language,
                onSave: preferences.save, onClose: { showSettings = false })
        }
        .preferredColorScheme(preferences.colorScheme)
        .environment(\.locale, Locale(identifier: preferences.state.preferences.language))
    }
    private func chooseFolder() {
        let picker = NSOpenPanel()
        picker.canChooseDirectories = true
        picker.canChooseFiles = false
        picker.allowsMultipleSelection = false
        picker.title = SyncWatchCopy.text("folder", language: preferences.state.preferences.language)
        picker.prompt = SyncWatchCopy.text("chooseFolder", language: preferences.state.preferences.language)
        picker.begin { response in
            if response == .OK, let url = picker.url { library.choose(url) }
        }
    }

}
