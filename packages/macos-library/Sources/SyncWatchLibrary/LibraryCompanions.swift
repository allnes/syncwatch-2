import Foundation

public enum LibraryCompanionKind: String, Sendable { case audio, subtitles }

/// A local scan version, never a room descriptor or a persisted native track ID.
public struct LocalCompanionFile: Sendable, Equatable {
    public let id: String
    public let kind: LibraryCompanionKind
    public let relativePath: String
    public let file: URL
    public let sizeBytes: Int64
    public let modificationDate: Date?

    public func open() throws -> LocalFileAccess {
        // Enumeration URLs cache resource values. Recreate the URL before checking the scan version.
        let current = URL(fileURLWithPath: file.path)
        let access = try LocalFileAccess.selected(current)
        let facts = try current.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
        guard facts.fileSize.map(Int64.init) == sizeBytes, facts.contentModificationDate == modificationDate else {
            throw CocoaError(.fileReadUnknown)
        }
        return access
    }
}
