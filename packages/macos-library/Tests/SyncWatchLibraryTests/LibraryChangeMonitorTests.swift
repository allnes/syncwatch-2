import Foundation
import Testing

@testable import SyncWatchLibrary

private struct MonitorCorpus: Decodable {
    let rootId: String
    let created: String
    let renamed: String
    let nested: String
    let content: String
    let replacement: String
}
private actor MonitorEvents {
    var changes = 0
    var unavailable = false
    func receive(_ event: LibraryMonitorEvent) {
        switch event {
        case .changed: changes += 1
        case .unavailable: unavailable = true
        }
    }
}

@Test func directoryMonitorReconcilesNativeChangesAndReleases() async throws {
    let fixture = URL(fileURLWithPath: ProcessInfo.processInfo.environment["SYNCWATCH_LIBRARY_FIXTURE"]!)
        .deletingLastPathComponent().appendingPathComponent("library-monitor.json")
    let corpus = try JSONDecoder().decode(MonitorCorpus.self, from: Data(contentsOf: fixture))
    for recursive in [false, true] {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let monitor = try LibraryChangeMonitor(root: root, recursive: recursive)
        let events = MonitorEvents()
        let observer = Task { for await event in monitor.changes { await events.receive(event) } }
        let scanner = FileSystemLibrary()
        func reconcile(after baseline: Int, paths: [String], size: Int? = nil) async throws {
            let deadline = ContinuousClock.now + .seconds(8)
            while true {
                let files = try await scanner.scan(root: root, rootID: corpus.rootId, recursive: recursive)
                if await events.changes > baseline, files.map(\.relativePath) == paths,
                    size == nil || files.first?.sizeBytes == Int64(size!)
                {
                    return
                }
                let count = await events.changes
                try #require(
                    ContinuousClock.now < deadline,
                    "Native invalidation did not reconcile: events=\(count), active=\(monitor.isActive), expected=\(paths), actual=\(files.map(\.relativePath))"
                )
                try await Task.sleep(for: .milliseconds(20))
            }
        }
        do {
            var baseline = await events.changes
            try Data(corpus.content.utf8).write(to: root.appendingPathComponent(corpus.created))
            try await reconcile(after: baseline, paths: [corpus.created])
            baseline = await events.changes
            try FileManager.default.moveItem(
                at: root.appendingPathComponent(corpus.created), to: root.appendingPathComponent(corpus.renamed))
            try await reconcile(after: baseline, paths: [corpus.renamed])
            baseline = await events.changes
            try Data(corpus.replacement.utf8).write(to: root.appendingPathComponent(corpus.renamed))
            try await reconcile(after: baseline, paths: [corpus.renamed], size: corpus.replacement.utf8.count)
            baseline = await events.changes
            let nested = root.appendingPathComponent(corpus.nested)
            try FileManager.default.createDirectory(
                at: nested.deletingLastPathComponent(), withIntermediateDirectories: true)
            try Data(corpus.content.utf8).write(to: nested)
            try await reconcile(
                after: baseline, paths: (recursive ? [corpus.nested, corpus.renamed] : [corpus.renamed]).sorted())
            baseline = await events.changes
            try FileManager.default.removeItem(at: root.appendingPathComponent(corpus.renamed))
            try await reconcile(after: baseline, paths: recursive ? [corpus.nested] : [])
            monitor.close()
            await observer.value
            #expect(!monitor.isActive)
            let final = await events.changes
            try Data(corpus.content.utf8).write(to: root.appendingPathComponent(corpus.created))
            #expect(await events.changes == final)
        } catch {
            monitor.close()
            await observer.value
            throw error
        }
    }
}

@Test func directoryMonitorReportsRemovedOrMovedRoot() async throws {
    for moved in [false, true] {
        let files = FileManager.default
        let scratch = files.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let root = scratch.appendingPathComponent("selected")
        try files.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? files.removeItem(at: scratch) }
        let monitor = try LibraryChangeMonitor(root: root, recursive: true)
        let events = MonitorEvents()
        let observer = Task { for await event in monitor.changes { await events.receive(event) } }
        do {
            if moved {
                try files.moveItem(at: root, to: scratch.appendingPathComponent("moved"))
            } else {
                try files.removeItem(at: root)
            }
            let deadline = ContinuousClock.now + .seconds(8)
            while await !events.unavailable {
                try #require(ContinuousClock.now < deadline, "Removed or moved root remained active")
                try await Task.sleep(for: .milliseconds(20))
            }
            #expect(!monitor.isActive)
            monitor.close()
            await observer.value
        } catch {
            monitor.close()
            await observer.value
            throw error
        }
    }
}
