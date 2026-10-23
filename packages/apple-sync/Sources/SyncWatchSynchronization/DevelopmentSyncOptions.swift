import CryptoKit
import Foundation

/// Explicit development selection. Receipt integrity is independent of release authentication and RoomMetadata authorization.
public struct DevelopmentSyncOptions: Sendable {
    public let runtime: URL
    public let executable: URL
    public let revision: String
    public let endpoint: SyncEndpoint
    public init(configuration: URL) throws {
        guard configuration.isFileURL,
            try configuration.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 65537 <= 65536
        else { throw SessionFailure.malformed }
        let data = try Data(contentsOf: configuration)
        let c = try WireValue(JSONSerialization.jsonObject(with: data)).object([
            "host", "port", "room", "username", "helperPackage",
        ])
        endpoint = try SyncEndpoint(
            host: c["host"]!.text(253), port: Int(c["port"]!.counter()), room: c["room"]!.text(256),
            username: c["username"]!.text())
        let path = try c["helperPackage"]!.text(4096)
        guard path.hasPrefix("/") else { throw SessionFailure.malformed }
        // Resolve the root once so Foundation's /tmp alias cannot invalidate containment checks.
        runtime = URL(filePath: path).resolvingSymlinksInPath().standardizedFileURL
        struct Report: Decodable {
            let target: String
            let syncplayRevision: String
            let files: [String: String]
        }
        let receipt = try JSONDecoder().decode(
            Report.self, from: Data(contentsOf: runtime.appendingPathComponent("helper-report.json")))
        guard receipt.target == "macos-arm64", receipt.syncplayRevision.count == 40,
            receipt.syncplayRevision.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }),
            receipt.files["bin/syncwatch-helper"] != nil,
            let entries = FileManager.default.enumerator(
                at: runtime, includingPropertiesForKeys: [.isSymbolicLinkKey, .isRegularFileKey])
        else { throw SessionFailure.malformed }
        var observed = Set<String>()
        for case let file as URL in entries {
            let values = try file.resourceValues(forKeys: [.isSymbolicLinkKey, .isRegularFileKey])
            guard values.isSymbolicLink != true else { throw SessionFailure.malformed }
            guard values.isRegularFile == true else { continue }
            let prefix = runtime.path + "/"
            guard file.path.hasPrefix(prefix) else { throw SessionFailure.malformed }
            let name = String(file.path.dropFirst(prefix.count))
            if name == "helper-report.json" { continue }
            guard let expected = receipt.files[name], observed.insert(name).inserted else {
                throw SessionFailure.malformed
            }
            let input = try FileHandle(forReadingFrom: file)
            defer { try? input.close() }
            var hash = SHA256()
            while let bytes = try input.read(upToCount: 1_048_576), !bytes.isEmpty { hash.update(data: bytes) }
            guard hash.finalize().map({ String(format: "%02x", $0) }).joined() == expected else {
                throw SessionFailure.malformed
            }
        }
        guard observed == Set(receipt.files.keys) else { throw SessionFailure.malformed }
        revision = receipt.syncplayRevision
        executable = runtime.appendingPathComponent("bin/syncwatch-helper")
    }
}
