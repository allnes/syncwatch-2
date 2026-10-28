import Foundation
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
        model.choose(first)
        await model.settled()
        let selected = try #require(model.presentation.selectedID)
        try Data("fixture".utf8).write(to: first.appendingPathComponent("Кино.Two.mkv"))
        try await refreshEventually { model.presentation.entries.count == 2 }
        #expect(model.presentation.selectedID == selected && store.count == 1)
        // A queued event from the old folder must not restore its authority after Choose.
        try Data("fixture".utf8).write(to: first.appendingPathComponent("old-only.mp4"))
        model.choose(second)
        await model.settled()
        try Data("fixture".utf8).write(to: second.appendingPathComponent("Кино.Two.mkv"))
        try await refreshEventually { model.presentation.entries.count == 2 }
        #expect(model.presentation.entries.map(\.title) == ["Кино.One.mkv", "Кино.Two.mkv"])
        #expect(model.selectedMedia()?.access.url.path == second.path && store.count == 2)
        await model.closeAndWait()
        guard case .loaded(var record) = try store.read() else { throw LibraryAccessError.invalidRecord }
        record.autoRefresh = false
        try store.write(record)
        let next = LibraryController(store: store)
        restored = next
        next.restore()
        await next.settled()
        let writes = store.count
        try Data("fixture".utf8).write(to: second.appendingPathComponent("manual.mp4"))
        try await Task.sleep(for: .seconds(1))
        #expect(next.presentation.entries.count == 2)
        next.rescan()
        await next.settled()
        #expect(next.presentation.entries.count == 3 && store.count == writes)
        await next.closeAndWait()
        #expect(next.presentation.enabledActions.isEmpty)
    } catch {
        await model.closeAndWait()
        await restored?.closeAndWait()
        throw error
    }
}
