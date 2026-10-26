import Foundation
import Testing

@testable import SyncWatchLibrary

@Test func fileContentHashingAndInvalidation() async throws {
    struct Corpus: Decodable {
        struct Item: Decodable {
            let name: String
            let content: String
            let `repeat`: Int
            let sha256: String
        }
        let cases: [Item]
    }
    let fixture = try #require(ProcessInfo.processInfo.environment["SYNCWATCH_LIBRARY_FIXTURE"])
    let path = URL(fileURLWithPath: fixture).deletingLastPathComponent().appendingPathComponent("library-content.json")
    let corpus = try JSONDecoder().decode(Corpus.self, from: Data(contentsOf: path))
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let movie = root.appendingPathComponent("owned 🎬.avi")
    let scanner = FileSystemLibrary()
    let hasher = FileContentHasher()
    let rootID = UUID().uuidString.lowercased()
    let timestamp = Date(timeIntervalSince1970: 1_600_000_000)
    var last: LocalMediaFile?
    for item in corpus.cases {
        let content = Data(String(repeating: item.content, count: item.repeat).utf8)
        try content.write(to: movie)
        try FileManager.default.setAttributes([.modificationDate: timestamp], ofItemAtPath: movie.path)
        let media = try #require(await scanner.scan(root: root, rootID: rootID, recursive: false).first)
        #expect(try await hasher.sha256(media) == item.sha256, "\(item.name)")
        let streamed = try await hasher.sha256(sizeBytes: Int64(content.count)) { offset, capacity in
            let start = Int(offset)
            return content.subdata(in: start..<min(content.count, start + capacity))
        }
        #expect(streamed == item.sha256, "\(item.name) scoped content")
        last = media
    }
    let media = try #require(last)
    for (size, response) in [(Int64(1), Data()), (0, Data([1])), (1, Data([1, 2]))] {
        do {
            _ = try await hasher.sha256(sizeBytes: size) { _, _ in response }
            Issue.record("Incomplete, oversized or trailing content accepted")
        } catch is CocoaError {}
    }
    try Data("longer".utf8).write(to: movie)
    do {
        _ = try await hasher.sha256(media)
        Issue.record("Stale catalog accepted")
    } catch is CocoaError {}
    try FileManager.default.removeItem(at: movie)
    do {
        _ = try await hasher.sha256(media)
        Issue.record("Missing file accepted")
    } catch is CocoaError {}
    let other = root.appendingPathComponent("other")
    try Data("xyz".utf8).write(to: other)
    try FileManager.default.createSymbolicLink(at: movie, withDestinationURL: other)
    do {
        _ = try await hasher.sha256(media)
        Issue.record("Symlink accepted")
    } catch is CocoaError {}
    let cancelled = Task {
        withUnsafeCurrentTask { $0?.cancel() }
        return try await hasher.sha256(media)
    }
    do {
        _ = try await cancelled.value
        Issue.record("Cancellation ignored")
    } catch is CancellationError {}
    // Removing the directory also checks that the owned file descriptor was released.
}
