import Foundation
import SyncWatchLibrary
import Testing

@testable import SyncWatch

private actor ControlledMetadata: MediaMetadataReading {
    private var waiting: [CheckedContinuation<MediaMetadata, Error>] = []
    private(set) var calls = 0
    private(set) var closed = false
    private var aborted = false
    func read(_ file: LocalMediaFile) async throws -> MediaMetadata {
        calls += 1
        if aborted { throw MediaMetadataFailure.unavailable }
        // Deliberately ignores cancellation to exercise the controller's stale-result boundary.
        return try await withCheckedThrowingContinuation { waiting.append($0) }
    }
    func complete(_ result: Result<MediaMetadata, Error>) { waiting.removeFirst().resume(with: result) }
    func abort() {
        aborted = true
        for item in waiting { item.resume(throwing: MediaMetadataFailure.unavailable) }
        waiting = []
    }
    func close() { closed = true }
    func entered(_ count: Int) async throws {
        let deadline = ContinuousClock.now.advanced(by: .seconds(2))
        while calls < count, ContinuousClock.now < deadline { try await Task.sleep(for: .milliseconds(5)) }
        try #require(calls == count)
    }
}

@Test @MainActor func libraryMetadataSelectionOwnership() async throws {
    let files = FileManager.default
    let scratch = files.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try files.createDirectory(at: scratch, withIntermediateDirectories: true)
    defer { try? files.removeItem(at: scratch) }
    for name in ["A.mkv", "B.mp4"] { try Data("fixture".utf8).write(to: scratch.appendingPathComponent(name)) }
    let reader = ControlledMetadata()
    let model = LibraryController(
        store: FileLibraryAccessStore(url: scratch.appendingPathComponent("state/access.json")), metadata: reader)
    do {
        model.choose(scratch)
        await model.settled()
        try await reader.entered(1)
        let revision = model.roomRevision
        let last = try #require(model.presentation.entries.last?.id)
        model.select(last)
        model.select(last)
        #expect(model.presentation.metadataLoading && model.presentation.metadataDurationMs == nil)
        #expect(await reader.calls == 1)  // No overlapping native inputs.
        let value = try MediaMetadata(durationMs: 60_000, width: 64, height: 48, audioTracks: 1, subtitleTracks: 0)
        await reader.complete(.success(value))
        try await reader.entered(2)
        #expect(model.presentation.selectedID == last && model.presentation.metadataDurationMs == nil)
        await reader.complete(.failure(MediaMetadataFailure.unavailable))
        try await reader.entered(3)
        await reader.complete(.success(value))
        await model.metadataSettled()
        #expect(model.presentation.entries.first?.durationMs == 60_000)
        #expect(model.presentation.entries.last?.durationMs == nil)
        #expect(model.presentation.metadataUnavailable && !model.presentation.metadataLoading && model.errorKey == nil)
        #expect(model.roomRevision == revision && model.selectedMedia()?.media.id == last)
        model.rescan()
        await model.settled()
        try await reader.entered(4)
        await reader.complete(.success(value))
        await model.metadataSettled()
        #expect(await reader.calls == 4)  // Unchanged background file reused after Refresh.
        #expect(model.presentation.metadataDurationMs == 60_000 && model.presentation.metadataAudioTracks == 1)
        #expect(model.presentation.metadataSubtitleTracks == 0 && !model.presentation.metadataUnavailable)
        try Data("changed fixture".utf8).write(to: scratch.appendingPathComponent("A.mkv"))
        model.rescan()
        await model.settled()
        try await reader.entered(5)
        await reader.complete(.success(value))
        try await reader.entered(6)  // Changed background version cannot reuse its old duration.
        #expect(model.presentation.entries.first?.durationMs == nil)
        let closing = Task { await model.closeAndWait() }
        await Task.yield()
        #expect(await !reader.closed)
        await reader.complete(.success(value))
        await closing.value
        #expect(await reader.closed)
        #expect(model.selectedMedia() == nil && model.presentation.enabledActions.isEmpty)
    } catch {
        await reader.abort()
        await model.closeAndWait()
        throw error
    }
}

@Test(
    .enabled(
        if: ProcessInfo.processInfo.environment["SYNCWATCH_METADATA_MEDIA"] != nil
            || ProcessInfo.processInfo.environment["SYNCWATCH_METADATA_FILE"] != nil))
func libraryMetadataRealVLC() async throws {
    let environment = ProcessInfo.processInfo.environment
    let package = try #require(environment["SYNCWATCH_METADATA_MEDIA"])
    let source = try #require(environment["SYNCWATCH_METADATA_FILE"])
    let files = FileManager.default
    let scratch = files.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try files.createDirectory(at: scratch, withIntermediateDirectories: true)
    defer { try? files.removeItem(at: scratch) }
    let clip = scratch.appendingPathComponent("Кино movie.avi")
    try files.copyItem(at: URL(filePath: source), to: clip)
    let broken = scratch.appendingPathComponent("broken.mkv")
    try Data("not a media container".utf8).write(to: broken)
    let scanner = FileSystemLibrary()
    let catalog = try await scanner.scan(root: scratch, rootID: UUID().uuidString.lowercased(), recursive: false)
    let good = try #require(catalog.first { $0.title == clip.lastPathComponent })
    let invalid = try #require(catalog.first { $0.title == broken.lastPathComponent })
    let reader = LibraryMetadataReader(media: MediaConfiguration(package: URL(filePath: package)))
    do {
        for _ in 0..<2 {
            let value = try await reader.read(good)
            #expect(value.durationMs == 60_000)
            #expect(value.width == 320)
            #expect(value.height == 180)
            #expect(value.audioTracks == 1 && value.subtitleTracks == 0)
        }
        do {
            _ = try await reader.read(invalid)
            Issue.record("Accepted invalid media")
        } catch {}
        let recovered = try await reader.read(good)
        #expect(recovered.durationMs == 60_000 && recovered.width == 320 && recovered.height == 180)
        let output = try FileHandle(forWritingTo: clip)
        try output.seekToEnd()
        try output.write(contentsOf: Data([0]))
        try output.close()
        do {
            _ = try await reader.read(good)
            Issue.record("Accepted changed media snapshot")
        } catch {}
        try files.removeItem(at: clip)
        do {
            _ = try await reader.read(good)
            Issue.record("Accepted missing media")
        } catch {}
        await reader.close()
    } catch {
        await reader.close()
        throw error
    }
}
