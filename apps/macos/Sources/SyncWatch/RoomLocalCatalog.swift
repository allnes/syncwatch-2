import Foundation
import SyncWatchDomain
import SyncWatchLibrary

/// Local file identifiers never become room identifiers. This map lives for one membership only.
@MainActor final class RoomLocalCatalog {
    struct Publication {
        let items: [MediaDescriptor]
        let localIDs: [String: String]
    }
    private var acknowledged: [String: String] = [:]
    private var pending: [String: String] = [:]
    func prepare(_ files: [LocalMediaFile], prepared: MediaDescriptor? = nil) throws -> Publication {
        let extra = prepared.map { value in files.contains { $0.id == value.mediaID } ? 0 : 1 } ?? 0
        guard files.count + extra <= 2048,
            prepared.map({ $0.fullHashSha256 != nil && ($0.durationMs ?? 0) > 0 }) ?? true
        else { throw ContractRejection.malformed }
        var next: [String: String] = [:]
        var items: [MediaDescriptor] = []
        func add(_ localID: String, title: String, size: Int64, duration: Int64?, hash: String?) throws {
            guard next[localID] == nil else { throw ContractRejection.malformed }
            let id = acknowledged[localID] ?? pending[localID] ?? "media-" + UUID().uuidString
            next[localID] = id
            items.append(
                try MediaDescriptor(
                    mediaID: id, title: title, titleKey: MediaDescriptor.normalizedTitleKey(title),
                    fileSizeBytes: size, durationMs: duration, fullHashSha256: hash))
        }
        for file in files {
            if let prepared, file.id == prepared.mediaID {
                try add(
                    file.id, title: prepared.title, size: prepared.fileSizeBytes,
                    duration: prepared.durationMs, hash: prepared.fullHashSha256)
            } else {
                try add(
                    file.id, title: MediaDescriptor.logicalTitle(file.title), size: file.sizeBytes, duration: nil,
                    hash: nil)
            }
        }
        // A loaded input can outlive removal from the scanned directory; its native owner retains the grant.
        if let prepared, next[prepared.mediaID] == nil {
            try add(
                prepared.mediaID, title: prepared.title, size: prepared.fileSizeBytes,
                duration: prepared.durationMs, hash: prepared.fullHashSha256)
        }
        pending = next
        return Publication(items: items, localIDs: next)
    }
    func acknowledge(_ publication: Publication) { acknowledged = publication.localIDs }
    func localID(for roomID: String) -> String? { acknowledged.first { $0.value == roomID }?.key }
    func roomID(for localID: String) -> String? { acknowledged[localID] }
}
