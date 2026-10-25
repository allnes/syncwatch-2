import Foundation
import Testing

@testable import SyncWatchLibrary

@Test func libraryAccessPersistence() throws {
    let files = FileManager.default
    let scratch = files.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try files.createDirectory(at: scratch, withIntermediateDirectories: true)
    defer { try? files.removeItem(at: scratch) }
    let selected = scratch.appendingPathComponent("selected")
    try files.createDirectory(at: selected, withIntermediateDirectories: false)
    let access = try LibraryFolderAccess.selected(selected)
    let record = try #require(access.record)
    let store = FileLibraryAccessStore(url: scratch.appendingPathComponent("state/library-access.json"))
    #expect(try store.read() == .missing)
    try store.write(record)
    #expect(try store.read() == .loaded(record))
    var changed = record
    changed.autoRefresh = false
    changed.scanSubfolders = false
    try store.write(changed)
    #expect(try store.read() == .loaded(changed))
    let valid = try Data(contentsOf: store.url)
    let validText = try #require(String(data: valid, encoding: .utf8))
    for replacement in ["1.0", "1e0"] {
        try Data(validText.replacingOccurrences(of: "\"version\":1", with: "\"version\":\(replacement)").utf8).write(
            to: store.url)
        #expect(try store.read() == .invalid)
    }
    let path = URL(fileURLWithPath: ProcessInfo.processInfo.environment["SYNCWATCH_LIBRARY_FIXTURE"]!)
        .deletingLastPathComponent().appendingPathComponent("library-access.json")
    let corpus = try JSONSerialization.jsonObject(with: Data(contentsOf: path)) as! [String: [[String: String]]]
    for entry in corpus["cases"]! {
        let bytes = Data(entry["text"]!.utf8)
        try bytes.write(to: store.url)
        if entry["status"] == "unsupportedVersion" {
            #expect(try store.read() == .unsupportedVersion)
            #expect(throws: LibraryAccessError.self) { try store.write(record) }
            #expect(try Data(contentsOf: store.url) == bytes)
        } else {
            #expect(try store.read() == .invalid, "\(entry["name"]!)")
        }
    }
    try Data(repeating: 32, count: FileLibraryAccessStore.maximumBytes + 1).write(to: store.url)
    #expect(try store.read() == .invalid)
    try Data([0xff]).write(to: store.url)
    #expect(try store.read() == .invalid)
    try store.write(record)
    let mode = try files.attributesOfItem(atPath: store.url.path)[.posixPermissions] as! NSNumber
    #expect(mode.intValue & 0o777 == 0o600)

    let moved = scratch.appendingPathComponent("moved")
    try files.moveItem(at: selected, to: moved)
    let restored = try LibraryFolderAccess.restore(record)
    #expect(restored.url.standardizedFileURL == moved.standardizedFileURL)
    #expect(restored.rootId == record.rootId)
    #expect(restored.record?.rootPath == restored.url.path)
    let corrupt = LibraryAccessRecord(rootId: record.rootId, rootPath: moved.path, bookmark: Data([1, 2, 3]))
    #expect(throws: (any Error).self) { _ = try LibraryFolderAccess.restore(corrupt) }
    // Read failures are not malformed data and must reach the application owner.
    try files.setAttributes([.posixPermissions: 0o000], ofItemAtPath: store.url.path)
    defer { try? files.setAttributes([.posixPermissions: 0o600], ofItemAtPath: store.url.path) }
    #expect(throws: (any Error).self) { _ = try store.read() }
}
