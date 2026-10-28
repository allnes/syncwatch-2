import Foundation
import SyncWatchDomain
import SyncWatchLibrary
import Testing

@testable import SyncWatch

private final class RefreshAccessStore: LibraryAccessStore, @unchecked Sendable {
    private let lock = NSLock()
    private var record: LibraryAccessRecord?
    private var writes = 0
    var count: Int { lock.withLock { writes } }
    func read() throws -> LibraryAccessRead { lock.withLock { record.map(LibraryAccessRead.loaded) ?? .missing } }
    func write(_ value: LibraryAccessRecord) throws {
        lock.withLock {
            record = value
            writes += 1
        }
    }
}

@MainActor private func refreshEventually(_ condition: () -> Bool) async throws {
    let deadline = ContinuousClock.now + .seconds(8)
    while !condition() {
        try #require(ContinuousClock.now < deadline, "Automatic catalog reconciliation timed out")
        try await Task.sleep(for: .milliseconds(20))
    }
}

@Test @MainActor func automaticLibraryRefreshPreservesOwnershipAndHonorsDisabledMode() async throws {
    let files = FileManager.default
    let scratch = files.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    let first = scratch.appendingPathComponent("first")
    let second = scratch.appendingPathComponent("second")
    try files.createDirectory(at: first, withIntermediateDirectories: true)
    try files.createDirectory(at: second, withIntermediateDirectories: true)
    defer { try? files.removeItem(at: scratch) }
    for root in [first, second] { try Data("fixture".utf8).write(to: root.appendingPathComponent("Кино.One.mkv")) }
    let store = RefreshAccessStore()
    let model = LibraryController(store: store)
    var restored: LibraryController?
    do {
        #expect(model.configureOptions(scanSubfolders: true, automaticRefresh: true))
        model.choose(first)
        await model.settled()
        let selected = try #require(model.presentation.selectedID)
        try Data("fixture".utf8).write(to: first.appendingPathComponent("Кино.Two.mkv"))
        try await refreshEventually { model.presentation.entries.count == 2 }
        #expect(model.presentation.selectedID == selected && store.count == 1)
        let roomRevision = model.roomRevision
        try Data("subtitle".utf8).write(to: first.appendingPathComponent("Кино.One.en.srt"))
        try await refreshEventually { model.selectedMedia()?.media.companions.count == 1 }
        #expect(model.roomRevision == roomRevision && store.count == 1)
        // A queued event from the old folder must not restore its authority after Choose.
        try Data("fixture".utf8).write(to: first.appendingPathComponent("old-only.mp4"))
        model.choose(second)
        await model.settled()
        try Data("fixture".utf8).write(to: second.appendingPathComponent("Кино.Two.mkv"))
        try await refreshEventually { model.presentation.entries.count == 2 }
        #expect(model.presentation.entries.map(\.title) == ["Кино.One.mkv", "Кино.Two.mkv"])
        #expect(model.selectedMedia()?.access.url.path == second.path && store.count == 2)
        await model.closeAndWait()
        let stateStore = FileLocalStateStore(url: scratch.appendingPathComponent("options/local-state.json"))
        let preferences = AppearancePreferences(store: stateStore)
        #expect(preferences.state.preferences.automaticRefresh == nil)
        #expect(
            preferences.save(
                [
                    "theme": "dark", "language": "ru", "scanSubfolders": "true", "automaticRefresh": "false",
                ], libraryOptions: true))
        #expect(await preferences.persistWatchState(LocalState()))
        let saved = AppearancePreferences(store: stateStore)
        #expect(saved.state.preferences.scanSubfolders == true && saved.state.preferences.automaticRefresh == false)
        let next = LibraryController(store: store)
        restored = next
        #expect(
            next.configureOptions(
                scanSubfolders: saved.state.preferences.scanSubfolders,
                automaticRefresh: saved.state.preferences.automaticRefresh))
        next.restore()
        await next.settled()
        let writes = store.count
        try Data("fixture".utf8).write(to: second.appendingPathComponent("manual.mp4"))
        try await Task.sleep(for: .seconds(1))
        #expect(next.presentation.entries.count == 2)
        next.rescan()
        await next.settled()
        #expect(next.presentation.entries.count == 3 && store.count == writes)
        var editor = next.settingsEditor(saved.editor)
        #expect(editor.values["automaticRefresh"] == "false" && editor.editableFields.contains("automaticRefresh"))
        editor.edit("scanSubfolders", value: "false")
        editor.edit("automaticRefresh", value: "true")
        #expect(editor.save { saved.save($0, libraryOptions: true) })
        #expect(
            next.configureOptions(
                scanSubfolders: saved.state.preferences.scanSubfolders,
                automaticRefresh: saved.state.preferences.automaticRefresh))
        await next.settled()
        try Data("fixture".utf8).write(to: second.appendingPathComponent("live.mp4"))
        try await refreshEventually { next.presentation.entries.count == 4 }
        let nested = second.appendingPathComponent("deep/ignored.mkv")
        try files.createDirectory(at: nested.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data("fixture".utf8).write(to: nested)
        next.rescan()
        await next.settled()
        #expect(next.presentation.entries.count == 4 && store.count == writes)
        let moved = scratch.appendingPathComponent("moved")
        try files.moveItem(at: second, to: moved)
        try await refreshEventually { next.errorKey == "libraryUnavailable" }
        try files.moveItem(at: moved, to: second)
        next.rescan()
        await next.settled()
        #expect(next.errorKey == nil && next.presentation.entries.count == 4)
        try Data("fixture".utf8).write(to: second.appendingPathComponent("recovered.mp4"))
        try await refreshEventually { next.presentation.entries.count == 5 }
        #expect(store.count == writes)
        await next.closeAndWait()
        #expect(next.presentation.enabledActions.isEmpty)
    } catch {
        await model.closeAndWait()
        await restored?.closeAndWait()
        throw error
    }
}
