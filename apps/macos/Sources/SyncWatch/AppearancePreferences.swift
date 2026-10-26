import AppKit
import Foundation
import SwiftUI
import SyncWatchDesign
import SyncWatchDomain
import SyncWatchLibrary

@MainActor final class AppearancePreferences: ObservableObject {
    @Published private(set) var state = LocalState()
    @Published private(set) var savingWatchState = false
    private(set) var canWrite = false
    private let store: SerializedLocalStateStore

    static var defaultURL: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("SyncWatch/local-state.json")
    }

    init(store: any LocalStateStore) {
        self.store = SerializedLocalStateStore(store)
        do {
            switch try self.store.read() {
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
            editableFields: canWrite && !savingWatchState ? ["theme", "language"] : [],
            canSave: canWrite && !savingWatchState)
    }

    func save(_ values: [String: String]) -> Bool {
        guard canWrite, !savingWatchState, let theme = values["theme"], let language = values["language"] else {
            return false
        }
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

    /// The WatchSession owner serializes checkpoints. Current appearance always wins the merge.
    func persistWatchState(_ value: LocalState) async -> Bool {
        guard !savingWatchState else { return false }
        var next = value
        next.preferences = state.preferences
        do { try next.validate() } catch { return false }
        state = next
        guard canWrite else { return false }
        savingWatchState = true
        defer { savingWatchState = false }
        let snapshot = next
        let destination = store
        return await Task.detached {
            do {
                try destination.write(snapshot)
                return true
            } catch { return false }
        }.value
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
    @StateObject private var room = RoomController()
    @StateObject private var watch: WatchSessionCoordinator
    private let lifecycle: ApplicationLifecycle
    init(lifecycle: ApplicationLifecycle) {
        self.lifecycle = lifecycle
        let stateURL: URL
        if let index = CommandLine.arguments.firstIndex(of: "--state-directory"),
            index + 1 < CommandLine.arguments.count
        {
            stateURL = URL(filePath: CommandLine.arguments[index + 1]).appendingPathComponent("local-state.json")
        } else {
            stateURL = AppearancePreferences.defaultURL
        }
        let preferences = AppearancePreferences(store: FileLocalStateStore(url: stateURL))
        _preferences = StateObject(wrappedValue: preferences)
        _watch = StateObject(
            wrappedValue: WatchSessionCoordinator(
                preferences: preferences, media: MediaConfiguration.read(CommandLine.arguments)))
        _library = StateObject(
            wrappedValue: LibraryController(
                store: FileLibraryAccessStore(
                    url: stateURL.deletingLastPathComponent().appendingPathComponent(
                        "library-access.json")),
                selectedID: preferences.state.selectedMediaID))
    }
    @State private var showRoom = false
    @State private var showSettings = false
    @State private var editor = SettingsEditor()

    var body: some View {
        ApplicationChrome(
            playerPresented: watch.playerPresented,
            library: AnyView(
                LibraryWorkspace(
                    presentation: room.libraryPresentation(watch.libraryPresentation(library.presentation)),
                    language: preferences.state.preferences.language
                ) { action, value in
                    if action == "chooseFolder" {
                        chooseFolder()
                    } else if action == "rescan" {
                        library.rescan()
                    } else if action == "selectMovie", let value {
                        library.select(value)
                    } else if action == "startWatching", let selection = library.selectedMedia() {
                        watch.start(selection)
                    } else if action == "continueWatching" {
                        watch.continueWatching()
                    } else if action == "endWatching" {
                        watch.end()
                    } else if action == "openRoom" {
                        showRoom = true
                    } else if action == "openSettings" {
                        editor = preferences.editor
                        showSettings = true
                    }
                }), player: playerContent
        )
        .background(WindowCloseGate(close: close))
        .onReceive(library.$roomRevision) { revision in
            room.updateLibrary(revision: revision, files: library.roomFiles)
        }
        .task {
            lifecycle.prepareForTermination = {
                [weak sessionOwner = watch, weak catalogOwner = library, weak roomOwner = room] in
                await sessionOwner?.close()
                await roomOwner?.close()
                catalogOwner?.close()
            }
            library.restore()
            await watch.prepareRuntime()
            await WatchAcceptance.run(preferences: preferences, library: library, watch: watch)
        }
        .onDisappear {
            let sessionOwner = watch
            let catalogOwner = library
            let roomOwner = room
            Task {
                await sessionOwner.close()
                await roomOwner.close()
                catalogOwner.close()
            }
        }
        .alert(
            SyncWatchCopy.text("brand", language: preferences.state.preferences.language),
            isPresented: Binding(
                get: { !WatchAcceptance.requested && (library.errorKey != nil || watch.errorKey != nil) },
                set: {
                    if !$0 {
                        library.errorKey = nil
                        watch.errorKey = nil
                    }
                })
        ) {
            Button(SyncWatchCopy.text("close", language: preferences.state.preferences.language)) {
                library.errorKey = nil
                watch.errorKey = nil
            }
        } message: {
            Text(
                SyncWatchCopy.text(
                    library.errorKey ?? watch.errorKey ?? "libraryUnavailable",
                    language: preferences.state.preferences.language))
        }
        .sheet(isPresented: $showSettings) {
            SettingsDialog(
                editor: $editor, language: preferences.state.preferences.language,
                onSave: { values in
                    let saved = preferences.save(values)
                    if saved { watch.preferencesChanged() }
                    return saved
                }, onClose: { showSettings = false })
        }
        .sheet(isPresented: $showRoom, onDismiss: { room.clearSecrets() }) {
            RoomConnectionSheet(room: room, language: preferences.state.preferences.language) {
                showRoom = false
            }
        }
        .preferredColorScheme(preferences.colorScheme)
        .environment(\.locale, Locale(identifier: preferences.state.preferences.language))
    }
    private var playerContent: AnyView {
        if let controller = watch.player {
            return AnyView(
                PlaybackPane(controller: controller, language: preferences.state.preferences.language)
                    .id(controller.scope.mediaGeneration))
        }
        return AnyView(EmptyView())
    }
    private func close() async {
        let sessionOwner = watch
        let catalogOwner = library
        await sessionOwner.close()
        await room.close()
        catalogOwner.close()
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
