import Foundation
import SyncWatchDomain
import Testing

@testable import SyncWatch

private final class TestStore: LocalStateStore {
    var current: LocalStateRead = .missing
    var failWrite = false
    var writes = 0
    func read() throws -> LocalStateRead { current }
    func write(_ state: LocalState) throws {
        if failWrite { throw CocoaError(.fileWriteNoPermission) }
        writes += 1
        current = .loaded(state)
    }
}

@MainActor @Test func appearanceSavePreservesSessionPreferencesAndAcknowledgesActualWrites() throws {
    let store = TestStore()
    var initial = LocalState()
    initial.preferences.skipSeconds = 42
    initial.selectedMediaID = "movie-1"
    initial.resumePositions = [ResumePosition(mediaID: "movie-1", positionMs: 9000)]
    store.current = .loaded(initial)
    let preferences = AppearancePreferences(store: store)
    #expect(preferences.editor.editableFields == ["theme", "language"])
    #expect(preferences.save(["theme": "dark", "language": "ru", "folder": "/not-persisted"]))
    #expect(store.writes == 1)
    #expect(preferences.state.preferences.theme == "dark" && preferences.state.preferences.language == "ru")
    #expect(preferences.state.preferences.skipSeconds == 42)
    #expect(preferences.state.resumePositions == initial.resumePositions)
    #expect(preferences.state.selectedMediaID == "movie-1")
    store.failWrite = true
    #expect(!preferences.save(["theme": "light", "language": "en"]))
    #expect(preferences.state.preferences.theme == "dark")
    #expect(!preferences.save(["theme": "invalid", "language": "en"]))
    #expect(store.writes == 1)
    store.current = .unsupportedVersion
    let future = AppearancePreferences(store: store)
    #expect(!future.canWrite && !future.editor.canSave)
    #expect(!future.save(["theme": "light", "language": "en"]))
    #expect(store.writes == 1)
}

@MainActor @Test func appearancePersistsAndRestoresThroughTheRealStore() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let store = FileLocalStateStore(url: directory.appendingPathComponent("local-state.json"))
    let preferences = AppearancePreferences(store: store)
    #expect(preferences.save(["theme": "light", "language": "ru"]))
    let restored = AppearancePreferences(store: store)
    #expect(restored.state.preferences.theme == "light")
    #expect(restored.state.preferences.language == "ru")
}
