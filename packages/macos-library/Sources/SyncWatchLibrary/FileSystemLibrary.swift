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
    public internal(set) var companions: [LocalCompanionFile] = []
    public internal(set) var folderMovie = false
}

/// The caller owns the selected folder grant for the complete scan/playback lifetime.
/// Failed or cancelled scans throw; callers publish only a completed snapshot.
public actor FileSystemLibrary {
    private static let extensions: Set<String> = [
        "mkv", "mp4", "avi", "mov", "m4v", "webm", "wmv", "mpg", "mpeg", "ts", "m2ts",
    ]
    private let companionExtensions: [String: LibraryCompanionKind]
    public init(companionExtensions: [String: LibraryCompanionKind] = [:]) {
        self.companionExtensions = companionExtensions
    }

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
        var companions: [LocalCompanionFile] = []
        var caseSensitive: [String: Bool] = [:]
        while let (directory, relativeDirectory) = pending.popLast() {
            try Task.checkCancellation()
            let children = try FileManager.default.contentsOfDirectory(
                at: directory, includingPropertiesForKeys: Array(keys))
            let names = Set(children.map(\.lastPathComponent))
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
                guard facts.isRegularFile == true, let dot = filename.lastIndex(of: ".")
                else { continue }
                let extensionName = String(filename[filename.index(after: dot)...])
                let video = Self.extensions.contains(extensionName.lowercased())
                let kind = companionExtensions[extensionName.lowercased()]
                guard video || kind != nil else { continue }
                guard let size = facts.fileSize, size >= 0 else { throw CocoaError(.fileReadUnknown) }
                let id = SHA256.hash(data: Data((rootID + "\0" + relative).utf8)).map { String(format: "%02x", $0) }
                    .joined()
                if let kind, !video {
                    companions.append(
                        LocalCompanionFile(
                            id: id, kind: kind, relativePath: relative, file: child, sizeBytes: Int64(size),
                            modificationDate: facts.contentModificationDate))
                    continue
                }
                if caseSensitive[relativeDirectory] == nil {
                    // Probe a known ASCII extension without creating a file or guessing from the OS.
                    let alternate =
                        String(filename[...dot])
                        + String(
                            extensionName.map {
                                $0.isUppercase ? Character($0.lowercased()) : Character($0.uppercased())
                            })
                    caseSensitive[relativeDirectory] =
                        names.contains(alternate)
                        || !FileManager.default.fileExists(atPath: directory.appendingPathComponent(alternate).path)
                }
                files.append(
                    LocalMediaFile(
                        id: id, title: filename,
                        relativePath: relative, file: child, sizeBytes: Int64(size),
                        modificationDate: facts.contentModificationDate))
            }
        }
        try Task.checkCancellation()
        let paths = files.map(\.relativePath)
        let audio = companions.filter { $0.kind == .audio }.map(\.relativePath)
        let subtitles = companions.filter { $0.kind == .subtitles }.map(\.relativePath)
        let sensitive = try LibraryFileIndex(videos: paths, audio: audio, subtitles: subtitles, caseSensitive: true)
        let insensitive = try LibraryFileIndex(videos: paths, audio: audio, subtitles: subtitles, caseSensitive: false)
        let byPath = Dictionary(uniqueKeysWithValues: companions.map { ($0.relativePath, $0) })
        for position in files.indices {
            try Task.checkCancellation()
            let path = files[position].relativePath
            let directory = path.lastIndex(of: "/").map { String(path[...$0]) } ?? ""
            let index = caseSensitive[directory] == false ? insensitive : sensitive
            files[position].companions = (index.audioPaths(for: path) + index.subtitlePaths(for: path)).compactMap {
                byPath[$0]
            }
            files[position].folderMovie = index.isFolderMovie(path)
        }
        return files.sorted { $0.relativePath.utf8.lexicographicallyPrecedes($1.relativePath.utf8) }
    }
}
