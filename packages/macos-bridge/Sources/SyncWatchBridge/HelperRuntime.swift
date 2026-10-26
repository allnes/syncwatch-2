import CryptoKit
import Darwin
import Foundation

/// Local development integrity, not a release signature or an atomic filesystem seal.
public struct HelperRuntime: Sendable {
    public static var expectedRevision: String { HelperRuntimePolicy.syncplayRevision }
    public let package: URL
    public let executable: URL
    public let revision: String

    public init(package: URL) throws {
        try Task.checkCancellation()
        guard package.isFileURL else { throw HelperSessionFailure.unavailable }
        guard try package.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink != true else {
            throw HelperSessionFailure.unavailable
        }
        guard package.isFileURL, let canonical = realpath(package.path, nil) else {
            throw HelperSessionFailure.unavailable
        }
        defer { free(canonical) }
        let root = URL(filePath: String(cString: canonical), directoryHint: .isDirectory)
        let resources: Set<URLResourceKey> = [.isRegularFileKey, .isDirectoryKey, .isSymbolicLinkKey]
        let rootValues = try root.resourceValues(forKeys: resources)
        let receipt = root.appendingPathComponent("helper-report.json")
        let receiptValues = try receipt.resourceValues(forKeys: resources.union([.fileSizeKey]))
        guard root.isFileURL, rootValues.isDirectory == true, rootValues.isSymbolicLink != true,
            receiptValues.isRegularFile == true, receiptValues.isSymbolicLink != true,
            (receiptValues.fileSize ?? Int.max) <= 16 * 1024 * 1024,
            let report = try JSONSerialization.jsonObject(with: Data(contentsOf: receipt)) as? [String: Any],
            report["schemaVersion"] as? Int == 1, report["target"] as? String == "macos-arm64",
            report["syncplayRevision"] as? String == HelperRuntimePolicy.syncplayRevision,
            report["developmentHelperOnly"] as? Bool == true,
            report["authenticatedInstallation"] as? Bool == false,
            let files = report["files"] as? [String: String], !files.isEmpty,
            files["bin/syncwatch-helper"] != nil, files["app/syncplay-revision.txt"] != nil
        else { throw HelperSessionFailure.unavailable }
        for (name, digest) in files {
            guard !name.contains("\\"), !name.contains(":"),
                name.unicodeScalars.allSatisfy({ $0.value >= 32 }),
                name.split(separator: "/", omittingEmptySubsequences: false).allSatisfy({
                    !$0.isEmpty && $0 != "." && $0 != ".."
                }),
                digest.range(of: "\\A[0-9a-f]{64}\\z", options: .regularExpression) != nil
            else { throw HelperSessionFailure.malformed }
        }
        guard let entries = FileManager.default.enumerator(at: root, includingPropertiesForKeys: Array(resources))
        else { throw HelperSessionFailure.unavailable }
        var observed = Set<String>()
        for case let file as URL in entries {
            try Task.checkCancellation()
            let values = try file.resourceValues(forKeys: resources)
            guard values.isSymbolicLink != true else { throw HelperSessionFailure.unavailable }
            if values.isDirectory == true { continue }
            guard values.isRegularFile == true else { throw HelperSessionFailure.unavailable }
            let name = String(file.path.dropFirst(root.path.count + 1))
            if name == "helper-report.json" { continue }
            guard observed.insert(name).inserted, let expected = files[name] else {
                throw HelperSessionFailure.unavailable
            }
            let input = try FileHandle(forReadingFrom: file)
            defer { try? input.close() }
            var hash = SHA256()
            while let chunk = try input.read(upToCount: 1_048_576), !chunk.isEmpty {
                try Task.checkCancellation()
                hash.update(data: chunk)
            }
            guard hash.finalize().map({ String(format: "%02x", $0) }).joined() == expected
            else { throw HelperSessionFailure.unavailable }
        }
        guard observed == Set(files.keys),
            FileManager.default.isExecutableFile(atPath: root.appendingPathComponent("bin/syncwatch-helper").path),
            try String(contentsOf: root.appendingPathComponent("app/syncplay-revision.txt"), encoding: .ascii)
                .trimmingCharacters(in: .whitespacesAndNewlines) == HelperRuntimePolicy.syncplayRevision
        else { throw HelperSessionFailure.unavailable }
        self.package = root
        executable = root.appendingPathComponent("bin/syncwatch-helper")
        revision = HelperRuntimePolicy.syncplayRevision
    }
}
