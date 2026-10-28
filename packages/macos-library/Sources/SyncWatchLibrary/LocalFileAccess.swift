import Foundation

/// A transient, explicitly selected file grant. Retain until every native borrower has stopped.
public final class LocalFileAccess: Sendable {
    public let file: URL
    private let scoped: Bool
    private init(_ file: URL) throws {
        let scoped = file.startAccessingSecurityScopedResource()
        do {
            let facts = try file.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
            guard facts.isRegularFile == true, facts.isSymbolicLink != true
            else { throw CocoaError(.fileReadNoSuchFile) }
            self.file = file
            self.scoped = scoped
        } catch {
            if scoped { file.stopAccessingSecurityScopedResource() }
            throw error
        }
    }
    public static func selected(_ file: URL) throws -> LocalFileAccess {
        guard file.isFileURL, file.host == nil || file.host == "", !file.path.utf8.contains(0) else {
            throw CocoaError(.fileReadInvalidFileName)
        }
        return try LocalFileAccess(file.standardizedFileURL)
    }
    deinit { if scoped { file.stopAccessingSecurityScopedResource() } }
}
