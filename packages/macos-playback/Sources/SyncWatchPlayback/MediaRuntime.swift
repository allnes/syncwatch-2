import CryptoKit
import Darwin
import Foundation

public enum PlaybackFailure: String, Error, Sendable {
    case invalid, unavailable, stale, engine, closed
}

/// Development integrity receipt, not a release signature or atomic filesystem seal.
public struct MediaRuntime: Sendable {
    public let library: URL
    public let revision: String

    public init(package: URL) throws {
        // Foundation shortens /private/tmp while its enumerator returns that
        // full spelling. Use a single filesystem spelling for receipt paths.
        guard package.isFileURL, let canonical = realpath(package.path, nil) else { throw PlaybackFailure.unavailable }
        defer { free(canonical) }
        let root = URL(filePath: String(cString: canonical), directoryHint: .isDirectory)
        guard root.isFileURL,
            let report = try JSONSerialization.jsonObject(
                with: Data(contentsOf: root.appendingPathComponent("build-report.json")))
                as? [String: Any],
            let sdk = report["sdk"] as? [String: Any], sdk["target"] as? String == "macos-arm64",
            let sources = report["sources"] as? [String: Any], let vlc = sources["vlc"] as? [String: Any],
            let revision = vlc["revision"] as? String, revision.count == 40,
            let files = report["files"] as? [String: String], !files.isEmpty,
            files["lib/libvlc.dylib"] != nil
        else { throw PlaybackFailure.unavailable }
        let resources: Set<URLResourceKey> = [.isRegularFileKey, .isDirectoryKey, .isSymbolicLinkKey]
        guard let entries = FileManager.default.enumerator(at: root, includingPropertiesForKeys: Array(resources))
        else {
            throw PlaybackFailure.unavailable
        }
        var observed: Set<String> = []
        for case let file as URL in entries {
            let values = try file.resourceValues(forKeys: resources)
            guard values.isSymbolicLink != true else { throw PlaybackFailure.unavailable }
            if values.isDirectory == true { continue }
            guard values.isRegularFile == true else { throw PlaybackFailure.unavailable }
            let name = String(file.path.dropFirst(root.path.count + 1))
            if name != "build-report.json" { observed.insert(name) }
        }
        guard observed == Set(files.keys) else { throw PlaybackFailure.unavailable }
        for (name, expected) in files {
            let pieces = name.split(separator: "/", omittingEmptySubsequences: false)
            guard !pieces.isEmpty, pieces.allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." }),
                !name.contains("\\"), !name.contains(":"), !name.contains("\0"),
                expected.count == 64
            else { throw PlaybackFailure.invalid }
            let file = root.appendingPathComponent(name)
            guard try file.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true
            else { throw PlaybackFailure.unavailable }
            let handle = try FileHandle(forReadingFrom: file)
            defer { try? handle.close() }
            var digest = SHA256()
            while let chunk = try handle.read(upToCount: 1_048_576), !chunk.isEmpty { digest.update(data: chunk) }
            let actual = digest.finalize().map { String(format: "%02x", $0) }.joined()
            guard actual == expected else { throw PlaybackFailure.unavailable }
        }
        self.library = root.appendingPathComponent("lib/libvlc.dylib")
        self.revision = revision
    }
}
