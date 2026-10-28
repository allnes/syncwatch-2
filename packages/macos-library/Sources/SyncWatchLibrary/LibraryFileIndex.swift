import Foundation

/// Relationships in one completed authorized listing. Paths remain local and root-relative.
public struct LibraryFileIndex: Sendable {
    private let caseSensitive: Bool
    private let videos: Set<String>
    private let videoCounts: [String: Int]
    private let extraDirectories: Set<String>
    private let audio: [String: [String]]
    private let subtitles: [String: [String]]

    public init(videos: [String], audio: [String], subtitles: [String], caseSensitive: Bool) throws {
        for path in videos + audio + subtitles {
            guard !path.isEmpty, !path.hasPrefix("/"), !path.utf8.contains(0),
                path.split(separator: "/", omittingEmptySubsequences: false).allSatisfy({
                    !$0.isEmpty && $0 != "." && $0 != ".."
                })
            else { throw CocoaError(.fileReadInvalidFileName) }
        }
        self.caseSensitive = caseSensitive
        self.videos = Set(videos)
        func key(_ value: String) -> String { caseSensitive ? value : value.lowercased() }
        var counts: [String: Int] = [:]
        var stems: Set<String> = []
        for path in videos {
            counts[Self.directory(path), default: 0] += 1
            let name = Self.name(path)
            stems.insert(key(name.lastIndex(of: ".").map { String(name[..<$0]) } ?? name))
        }
        var extras: Set<String> = []
        for path in audio + subtitles {
            let directory = Self.directory(path)
            extras.insert(directory)
            if !directory.isEmpty { extras.insert(Self.directory(directory)) }
        }
        func index(_ paths: [String]) -> [String: [String]] {
            var result: [String: [String]] = [:]
            let ordered = paths.sorted {
                let a = Self.name($0)
                let b = Self.name($1)
                return a == b ? $0.utf8.lexicographicallyPrecedes($1.utf8) : a.utf8.lexicographicallyPrecedes(b.utf8)
            }
            for path in ordered {
                let name = Self.name(path)
                for dot in name.indices where name[dot] == "." {
                    let prefix = key(String(name[..<dot]))
                    if stems.contains(prefix) { result[prefix, default: []].append(path) }
                }
            }
            return result
        }
        videoCounts = counts
        extraDirectories = extras
        self.audio = index(audio)
        self.subtitles = index(subtitles)
    }
    public func isFolderMovie(_ video: String) -> Bool {
        guard videos.contains(video) else { return false }
        let directory = Self.directory(video)
        return videoCounts[directory] == 1 && extraDirectories.contains(directory)
    }
    public func audioPaths(for video: String) -> [String] { videos.contains(video) ? audio[stem(video)] ?? [] : [] }
    public func subtitlePaths(for video: String) -> [String] {
        videos.contains(video) ? subtitles[stem(video)] ?? [] : []
    }
    private func key(_ value: String) -> String { caseSensitive ? value : value.lowercased() }
    private func stem(_ path: String) -> String {
        let name = Self.name(path)
        return key(name.lastIndex(of: ".").map { String(name[..<$0]) } ?? name)
    }
    private static func name(_ path: String) -> String {
        path.lastIndex(of: "/").map { String(path[path.index(after: $0)...]) } ?? path
    }
    private static func directory(_ path: String) -> String {
        path.lastIndex(of: "/").map { String(path[..<$0]) } ?? ""
    }
}
