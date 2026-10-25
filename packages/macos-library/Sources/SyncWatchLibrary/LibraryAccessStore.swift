import CoreFoundation
import Darwin
import Foundation

public enum LibraryAccessError: Error { case invalidRecord, unsupportedVersion }

/// Local access metadata. A bookmark must still be resolved by the platform access owner.
public struct LibraryAccessRecord: Codable, Equatable, Sendable {
    public var version = 1
    public var platform = "macos"
    public let rootId: String
    public let rootPath: String
    public let bookmark: Data
    public var scanSubfolders: Bool
    public var autoRefresh: Bool

    public init(rootId: String, rootPath: String, bookmark: Data, scanSubfolders: Bool = true, autoRefresh: Bool = true)
    {
        self.rootId = rootId
        self.rootPath = rootPath
        self.bookmark = bookmark
        self.scanSubfolders = scanSubfolders
        self.autoRefresh = autoRefresh
    }
    public func validate() throws {
        guard version == 1, platform == "macos", UUID(uuidString: rootId)?.uuidString.lowercased() == rootId,
            rootPath.hasPrefix("/"), !rootPath.utf8.contains(0), !bookmark.isEmpty
        else { throw LibraryAccessError.invalidRecord }
    }
}

public enum LibraryAccessRead: Equatable, Sendable {
    case missing
    case loaded(LibraryAccessRecord)
    case invalid, unsupportedVersion
}

/// The caller selects an application-owned file and serializes access off the UI thread.
public protocol LibraryAccessStore: Sendable {
    func read() throws -> LibraryAccessRead
    func write(_ record: LibraryAccessRecord) throws
}

public struct FileLibraryAccessStore: LibraryAccessStore {
    public let url: URL
    public init(url: URL) { self.url = url.standardizedFileURL }
    public static let maximumBytes = 262_144
    private static let keys: Set<String> = [
        "version", "platform", "rootId", "rootPath", "bookmark", "scanSubfolders", "autoRefresh",
    ]

    public func read() throws -> LibraryAccessRead {
        let data: Data
        do {
            let file = try FileHandle(forReadingFrom: url)
            defer { try? file.close() }
            data = try file.read(upToCount: Self.maximumBytes + 1) ?? Data()
        } catch let error as NSError
            where error.domain == NSCocoaErrorDomain
            && [NSFileReadNoSuchFileError, NSFileNoSuchFileError].contains(error.code)
        { return .missing }
        guard data.count <= Self.maximumBytes, String(data: data, encoding: .utf8) != nil,
            !data.contains(0), !data.starts(with: [0xef, 0xbb, 0xbf])
        else { return .invalid }
        do {
            guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                Self.rootPairs(data) == object.count,
                let version = object["version"] as? NSNumber,
                CFGetTypeID(version) != CFBooleanGetTypeID(), !["f", "d"].contains(String(cString: version.objCType)),
                (0...Int64(Int32.max)).contains(version.int64Value)
            else { return .invalid }
            guard version.intValue == 1 else { return .unsupportedVersion }
            guard Set(object.keys) == Self.keys else { return .invalid }
            let record = try JSONDecoder().decode(LibraryAccessRecord.self, from: data)
            try record.validate()
            return .loaded(record)
        } catch { return .invalid }
    }
    public func write(_ record: LibraryAccessRecord) throws {
        try record.validate()
        guard try read() != .unsupportedVersion else { throw LibraryAccessError.unsupportedVersion }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(record)
        guard data.count <= Self.maximumBytes else { throw LibraryAccessError.invalidRecord }
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(), withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700])
        let temporary = url.deletingLastPathComponent().appendingPathComponent(
            ".library-access-" + UUID().uuidString + ".tmp")
        defer { try? FileManager.default.removeItem(at: temporary) }
        guard
            FileManager.default.createFile(
                atPath: temporary.path, contents: data, attributes: [.posixPermissions: 0o600])
        else { throw CocoaError(.fileWriteUnknown) }
        let file = try FileHandle(forWritingTo: temporary)
        do {
            try file.synchronize()
            try file.close()
        } catch {
            try? file.close()
            throw error
        }
        guard rename(temporary.path, url.path) == 0 else {
            throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno))
        }
    }
    // Foundation validates JSON syntax; count root members to reject duplicate keys,
    // including escaped aliases, before a dictionary can discard one occurrence.
    private static func rootPairs(_ data: Data) -> Int {
        var depth = 0
        var count = 0
        var quoted = false
        var escaped = false
        for byte in data {
            if quoted {
                if escaped {
                    escaped = false
                } else if byte == 92 {
                    escaped = true
                } else if byte == 34 {
                    quoted = false
                }
            } else {
                switch byte {
                case 34: quoted = true
                case 123, 91: depth += 1
                case 125, 93: depth -= 1
                case 58: if depth == 1 { count += 1 }
                default: break
                }
            }
        }
        return count
    }
}
