import Foundation
import Testing

@testable import SyncWatchLibrary

private struct CompanionScanCorpus: Decodable {
    let rootId: String
    let files: [String]
    let expected: [String: [String]]
    let insensitiveExtra: String
    let folderMovies: [String]
    let notFolderMovies: [String]
}

@Test func companionScanUsesLocalNamingAndRejectsStaleFiles() async throws {
    let fixture = URL(fileURLWithPath: ProcessInfo.processInfo.environment["SYNCWATCH_LIBRARY_FIXTURE"]!)
        .deletingLastPathComponent().appendingPathComponent("library-companion-scan.json")
    let corpus = try JSONDecoder().decode(CompanionScanCorpus.self, from: Data(contentsOf: fixture))
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    for name in corpus.files {
        let path = root.appendingPathComponent(name)
        try FileManager.default.createDirectory(at: path.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data(name.utf8).write(to: path)
    }
    try FileManager.default.createSymbolicLink(
        at: root.appendingPathComponent("Movie.Part.1.link.srt"),
        withDestinationURL: root.appendingPathComponent("Movie.Part.1.en.srt"))
    let scanner = FileSystemLibrary(companionExtensions: ["srt": .subtitles, "wav": .audio])
    let files = try await scanner.scan(root: root, rootID: corpus.rootId, recursive: true)
    let insensitive = FileManager.default.fileExists(atPath: root.appendingPathComponent("mOvIe.PaRt.1.mkv").path)
    for file in files {
        var expected = corpus.expected[file.relativePath] ?? []
        if insensitive, file.title == "Movie.Part.1.mkv" { expected.append(corpus.insensitiveExtra) }
        #expect(file.companions.map(\.relativePath) == expected)
        if corpus.folderMovies.contains(file.relativePath) { #expect(file.folderMovie) }
        if corpus.notFolderMovies.contains(file.relativePath) { #expect(!file.folderMovie) }
        #expect(file.companions.allSatisfy { $0.id != file.id && $0.sizeBytes > 0 })
    }
    let movie = try #require(files.first { $0.relativePath == "Movie.Part.1.mkv" })
    let subtitle = try #require(movie.companions.first { $0.kind == .subtitles })
    let access = try subtitle.open()
    #expect(access.file.path == subtitle.file.standardizedFileURL.path)
    try Data("changed".utf8).write(to: subtitle.file)
    #expect(throws: CocoaError.self) { try subtitle.open() }
    let updated = try await scanner.scan(root: root, rootID: corpus.rootId, recursive: true)
    let next = try #require(updated.first { $0.id == movie.id }?.companions.first { $0.id == subtitle.id })
    #expect(next.sizeBytes == 7 && next != subtitle)
    try FileManager.default.removeItem(at: next.file)
    #expect(throws: CocoaError.self) { try next.open() }
    let flat = try await scanner.scan(root: root, rootID: corpus.rootId, recursive: false)
    #expect(flat.count == 1 && flat[0].companions.isEmpty && !flat[0].folderMovie)
}
