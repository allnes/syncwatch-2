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
    func prepare(_ files: [LocalMediaFile]) throws -> Publication {
        guard files.count <= 2048 else { throw ContractRejection.malformed }
        var next: [String: String] = [:]
        let items = try files.map { file in
            guard next[file.id] == nil else { throw ContractRejection.malformed }
            let id = acknowledged[file.id] ?? pending[file.id] ?? "media-" + UUID().uuidString
            next[file.id] = id
            let title = MediaDescriptor.logicalTitle(file.title)
            return try MediaDescriptor(
                mediaID: id, title: title, titleKey: MediaDescriptor.normalizedTitleKey(title),
                fileSizeBytes: file.sizeBytes, durationMs: nil, fullHashSha256: nil)
        }
        pending = next
        return Publication(items: items, localIDs: next)
    }
    func acknowledge(_ publication: Publication) { acknowledged = publication.localIDs }
    func localID(for roomID: String) -> String? { acknowledged.first { $0.value == roomID }?.key }
}
