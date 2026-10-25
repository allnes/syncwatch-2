import Foundation

/// Retain this owner through scanning and native playback; its scope ends on final release.
public final class LibraryFolderAccess: Sendable {
    public let rootId: String
    public let url: URL
    public let record: LibraryAccessRecord?
    public let scanSubfolders: Bool
    public let autoRefresh: Bool
    private let scoped: Bool

    private init(url: URL, rootId: String, scanSubfolders: Bool, autoRefresh: Bool) throws {
        let scoped = url.startAccessingSecurityScopedResource()
        do {
            guard try url.resourceValues(forKeys: [.isDirectoryKey]).isDirectory == true else {
                throw CocoaError(.fileReadNoSuchFile)
            }
            self.url = url
            self.rootId = rootId
            self.scoped = scoped
            self.scanSubfolders = scanSubfolders
            self.autoRefresh = autoRefresh
            // A failed bookmark prevents persistence, while the current picker grant remains usable.
            let bookmark = try? url.bookmarkData(
                options: [.withSecurityScope, .securityScopeAllowOnlyReadAccess],
                includingResourceValuesForKeys: nil, relativeTo: nil)
            self.record = bookmark.map {
                LibraryAccessRecord(
                    rootId: rootId, rootPath: url.path, bookmark: $0,
                    scanSubfolders: scanSubfolders, autoRefresh: autoRefresh)
            }
        } catch {
            if scoped { url.stopAccessingSecurityScopedResource() }
            throw error
        }
    }
    public static func selected(_ url: URL, scanSubfolders: Bool = true, autoRefresh: Bool = true) throws
        -> LibraryFolderAccess
    {
        guard url.isFileURL, url.path.hasPrefix("/"), !url.path.utf8.contains(0) else {
            throw LibraryAccessError.invalidRecord
        }
        return try LibraryFolderAccess(
            url: url.standardizedFileURL, rootId: UUID().uuidString.lowercased(),
            scanSubfolders: scanSubfolders, autoRefresh: autoRefresh)
    }
    public static func restore(_ record: LibraryAccessRecord) throws -> LibraryFolderAccess {
        try record.validate()
        var stale = false
        let url = try URL(
            resolvingBookmarkData: record.bookmark, options: [.withSecurityScope, .withoutUI],
            relativeTo: nil, bookmarkDataIsStale: &stale)
        // Always renew while access is active. A saved path is never a fallback grant.
        return try LibraryFolderAccess(
            url: url, rootId: record.rootId,
            scanSubfolders: record.scanSubfolders, autoRefresh: record.autoRefresh)
    }
    deinit { if scoped { url.stopAccessingSecurityScopedResource() } }
}
