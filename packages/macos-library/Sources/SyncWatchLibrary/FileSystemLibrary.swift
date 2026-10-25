import CryptoKit
import Foundation

/// Local filesystem facts. Paths and timestamps never form a peer media descriptor.
public struct LocalMediaFile: Sendable, Equatable {
    public let id: String
    public let title: String
    public let relativePath: String
    public let file: URL
    public let sizeBytes: Int64
    public let modificationDate: Date?
}

/// The caller owns the selected folder grant for the complete scan/playback lifetime.
/// Failed or cancelled scans throw; callers publish only a completed snapshot.
public actor FileSystemLibrary {
    private static let extensions: Set<String> = [
        "mkv", "mp4", "avi", "mov", "m4v", "webm", "wmv", "mpg", "mpeg", "ts", "m2ts",
    ]
    public init() {}

    public func scan(root: URL, rootID: String, recursive: Bool) async throws -> [LocalMediaFile] {
        guard UUID(uuidString: rootID)?.uuidString.lowercased() == rootID,
            root.isFileURL, root.path.hasPrefix("/")
        else { throw CocoaError(.fileReadInvalidFileName) }
        let root = root.standardizedFileURL
        let keys: Set<URLResourceKey> = [
            .isDirectoryKey, .isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey, .contentModificationDateKey,
        ]
        guard try root.resourceValues(forKeys: keys).isDirectory == true else { throw CocoaError(.fileReadNoSuchFile) }
        var pending: [(URL, String)] = [(root, "")]
        var files: [LocalMediaFile] = []
        while let (directory, relativeDirectory) = pending.popLast() {
            try Task.checkCancellation()
            let children = try FileManager.default.contentsOfDirectory(
                at: directory, includingPropertiesForKeys: Array(keys))
            for child in children {
                try Task.checkCancellation()
                let facts = try child.resourceValues(forKeys: keys)
                if facts.isSymbolicLink == true { continue }
                let relative = relativeDirectory + child.lastPathComponent
                if facts.isDirectory == true {
                    if recursive { pending.append((child, relative + "/")) }
                    continue
                }
                let filename = child.lastPathComponent
                guard facts.isRegularFile == true, let dot = filename.lastIndex(of: "."),
                    Self.extensions.contains(String(filename[filename.index(after: dot)...]).lowercased())
                else { continue }
                guard let size = facts.fileSize, size >= 0 else { throw CocoaError(.fileReadUnknown) }
                let id = SHA256.hash(data: Data((rootID + "\0" + relative).utf8)).map { String(format: "%02x", $0) }
                    .joined()
                files.append(
                    LocalMediaFile(
                        id: id, title: filename,
                        relativePath: relative, file: child, sizeBytes: Int64(size),
                        modificationDate: facts.contentModificationDate))
            }
        }
        try Task.checkCancellation()
        return files.sorted { $0.relativePath.utf8.lexicographicallyPrecedes($1.relativePath.utf8) }
    }
}
