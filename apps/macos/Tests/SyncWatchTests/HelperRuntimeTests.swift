import CryptoKit
import Foundation
import SyncWatchBridge
import Testing

@testable import SyncWatch

@Test func helperRuntimeRejectsChangedOrUnpinnedPackages() async throws {
    let temporary = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: temporary) }
    let cases = [
        "valid", "wrongTarget", "wrongPin", "wrongRevisionFile", "changedFile", "extraFile", "missingFile",
        "pathEscape", "entrySymlink",
    ]
    for name in cases {
        let root = temporary.appendingPathComponent(name)
        try FileManager.default.createDirectory(
            at: root.appendingPathComponent("bin"), withIntermediateDirectories: true)
        try FileManager.default.createDirectory(
            at: root.appendingPathComponent("app"), withIntermediateDirectories: true)
        let executable = root.appendingPathComponent("bin/syncwatch-helper")
        try Data("owned test stub; never executed".utf8).write(to: executable)
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: executable.path)
        let revision = root.appendingPathComponent("app/syncplay-revision.txt")
        try Data(
            ((name == "wrongRevisionFile" ? String(repeating: "0", count: 40) : HelperRuntime.expectedRevision) + "\n")
                .utf8
        ).write(to: revision)
        var files: [String: String] = [:]
        for relative in ["bin/syncwatch-helper", "app/syncplay-revision.txt"] {
            files[relative] = SHA256.hash(data: try Data(contentsOf: root.appendingPathComponent(relative))).map {
                String(format: "%02x", $0)
            }.joined()
        }
        if name == "pathEscape" { files["../outside"] = String(repeating: "a", count: 64) }
        let report: [String: Any] = [
            "schemaVersion": 1, "target": name == "wrongTarget" ? "linux-x64" : "macos-arm64",
            "syncplayRevision": name == "wrongPin" ? String(repeating: "0", count: 40) : HelperRuntime.expectedRevision,
            "developmentHelperOnly": true, "authenticatedInstallation": false, "files": files,
        ]
        try JSONSerialization.data(withJSONObject: report).write(to: root.appendingPathComponent("helper-report.json"))
        if name == "changedFile" { try Data("changed".utf8).write(to: executable) }
        if name == "extraFile" { try Data().write(to: root.appendingPathComponent("extra")) }
        if name == "missingFile" { try FileManager.default.removeItem(at: executable) }
        if name == "entrySymlink" {
            try FileManager.default.createSymbolicLink(
                at: root.appendingPathComponent("link"), withDestinationURL: executable)
        }
        do {
            let result = try HelperRuntime(package: root)
            #expect(name == "valid")
            #expect(result.revision == HelperRuntime.expectedRevision)
            _ = try HelperRuntime(package: root)
        } catch { #expect(name != "valid") }
    }
    let cancelled = Task {
        while !Task.isCancelled { await Task.yield() }
        return try HelperRuntime(package: temporary.appendingPathComponent("valid"))
    }
    cancelled.cancel()
    do {
        _ = try await cancelled.value
        Issue.record("Cancelled helper verification succeeded")
    } catch is CancellationError {}
    if let real = ProcessInfo.processInfo.environment["SYNCWATCH_VERIFY_HELPER_PACKAGE"] {
        _ = try HelperRuntime(package: URL(filePath: real))
    }
    if let derivative = ProcessInfo.processInfo.environment["SYNCWATCH_REJECT_HELPER_PACKAGE"] {
        do {
            _ = try HelperRuntime(package: URL(filePath: derivative))
            Issue.record("Instrumented test package was admitted")
        } catch {}
    }
}
