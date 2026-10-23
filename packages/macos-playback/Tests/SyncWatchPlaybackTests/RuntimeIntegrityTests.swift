import CryptoKit
import Foundation
import SyncWatchPlayback
import Testing

@Test func temporaryDirectoryAliasAndUnexpectedPluginAreHandled() throws {
    let root = URL(filePath: "/tmp/SyncWatch-runtime-" + UUID().uuidString, directoryHint: .isDirectory)
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createDirectory(at: root.appendingPathComponent("lib"), withIntermediateDirectories: true)
    let bytes = Data("integrity-fixture-only".utf8)
    let library = root.appendingPathComponent("lib/libvlc.dylib")
    try bytes.write(to: library)
    let digest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
    let receipt: [String: Any] = [
        "sdk": ["target": "macos-arm64"],
        "sources": ["vlc": ["revision": String(repeating: "a", count: 40)]],
        "files": ["lib/libvlc.dylib": digest],
    ]
    try JSONSerialization.data(withJSONObject: receipt).write(to: root.appendingPathComponent("build-report.json"))
    let verified = try MediaRuntime(package: root)
    #expect(verified.library.path.hasPrefix("/private/tmp/"))
    let extra = root.appendingPathComponent("lib/extra.dylib")
    try bytes.write(to: extra)
    #expect(throws: PlaybackFailure.unavailable) { try MediaRuntime(package: root) }
    try FileManager.default.removeItem(at: extra)
    try Data("changed".utf8).write(to: library)
    #expect(throws: PlaybackFailure.unavailable) { try MediaRuntime(package: root) }
    try bytes.write(to: library)
    #expect(try MediaRuntime(package: root).revision == String(repeating: "a", count: 40))
}
