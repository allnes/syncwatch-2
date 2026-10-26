import CryptoKit
import Darwin
import Foundation

/// Serialized, bounded background hashing. The caller retains the folder grant.
public actor FileContentHasher {
    private struct Snapshot: Equatable {
        let device: dev_t
        let inode: ino_t
        let size: Int64
        let modifiedSeconds: Int
        let modifiedNanos: Int
        let changedSeconds: Int
        let changedNanos: Int
        init(_ value: stat) throws {
            guard value.st_mode & S_IFMT == S_IFREG else { throw CocoaError(.fileReadUnsupportedScheme) }
            device = value.st_dev
            inode = value.st_ino
            size = value.st_size
            modifiedSeconds = value.st_mtimespec.tv_sec
            modifiedNanos = value.st_mtimespec.tv_nsec
            changedSeconds = value.st_ctimespec.tv_sec
            changedNanos = value.st_ctimespec.tv_nsec
        }
        static func descriptor(_ descriptor: Int32) throws -> Self {
            var value = stat()
            guard fstat(descriptor, &value) == 0 else { throw CocoaError(.fileReadUnknown) }
            return try Self(value)
        }
        static func path(_ path: String) throws -> Self {
            var value = stat()
            guard lstat(path, &value) == 0 else { throw CocoaError(.fileReadNoSuchFile) }
            return try Self(value)
        }
    }
    public init() {}

    /// The caller owns and validates the source version; no path is reopened here.
    public func sha256(
        sizeBytes: Int64, readChunk: @Sendable (Int64, Int) async throws -> Data
    ) async throws -> String {
        guard sizeBytes >= 0 else { throw CocoaError(.fileReadUnknown) }
        var hash = SHA256()
        var offset: Int64 = 0
        while offset < sizeBytes {
            try Task.checkCancellation()
            let capacity = Int(min(262_144, sizeBytes - offset))
            let chunk = try await readChunk(offset, capacity)
            guard !chunk.isEmpty, chunk.count <= capacity else { throw CocoaError(.fileReadUnknown) }
            hash.update(data: chunk)
            offset += Int64(chunk.count)
        }
        try Task.checkCancellation()
        guard try await readChunk(sizeBytes, 1).isEmpty else { throw CocoaError(.fileReadUnknown) }
        try Task.checkCancellation()
        return hash.finalize().map { String(format: "%02x", $0) }.joined()
    }

    public func sha256(_ media: LocalMediaFile) async throws -> String {
        try Task.checkCancellation()
        let fd = Darwin.open(media.file.path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK)
        guard fd >= 0 else { throw CocoaError(.fileReadNoPermission) }
        let file = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
        defer { try? file.close() }
        let before = try Snapshot.descriptor(fd)
        let facts = try media.file.resourceValues(forKeys: [.contentModificationDateKey])
        guard before.size == media.sizeBytes, facts.contentModificationDate == media.modificationDate,
            try Snapshot.path(media.file.path) == before
        else { throw CocoaError(.fileReadUnknown) }
        var hash = SHA256()
        var total: Int64 = 0
        while let chunk = try file.read(upToCount: 262_144), !chunk.isEmpty {
            try Task.checkCancellation()
            total += Int64(chunk.count)
            guard total <= before.size else { throw CocoaError(.fileReadUnknown) }
            hash.update(data: chunk)
        }
        try Task.checkCancellation()
        guard total == before.size, try Snapshot.descriptor(fd) == before,
            try Snapshot.path(media.file.path) == before
        else { throw CocoaError(.fileReadUnknown) }
        let digest = hash.finalize().map { String(format: "%02x", $0) }.joined()
        return digest
    }
}
