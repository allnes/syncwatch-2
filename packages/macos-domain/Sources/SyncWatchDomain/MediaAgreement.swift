import Foundation

/// Peer-safe catalog facts. Local paths and file grants never enter this value.
public struct MediaDescriptor: Sendable, Equatable {
    public let mediaID: String
    public let title: String
    public let titleKey: String
    public let fileSizeBytes: Int64
    public let durationMs: Int64?
    public let fullHashSha256: String?

    public init(
        mediaID: String, title: String, titleKey: String, fileSizeBytes: Int64,
        durationMs: Int64?, fullHashSha256: String?
    ) throws {
        _ = try PlaybackScope(clientRunID: mediaID, mediaGeneration: 0)
        func text(_ value: String) -> Bool {
            (1...256).contains(value.unicodeScalars.count)
                && value.unicodeScalars.allSatisfy { $0.value >= 32 && $0.value != 127 }
        }
        guard text(title), text(titleKey), titleKey == Self.normalizedTitleKey(title),
            (1...Int64(PlaybackScope.maximumGeneration)).contains(fileSizeBytes),
            durationMs.map({ (0...WatchSession.maximumPositionMs).contains($0) }) ?? true,
            fullHashSha256.map({ $0.range(of: "\\A[0-9a-f]{64}\\z", options: .regularExpression) != nil }) ?? true
        else { throw ContractRejection.malformed }
        self.mediaID = mediaID
        self.title = title
        self.titleKey = titleKey
        self.fileSizeBytes = fileSizeBytes
        self.durationMs = durationMs
        self.fullHashSha256 = fullHashSha256
    }

    /// The v1 service folds ASCII case only, after NFC and ASCII-space collapse.
    public static func normalizedTitleKey(_ title: String) -> String {
        let collapsed = title.precomposedStringWithCanonicalMapping.split(separator: " ").joined(separator: " ")
        return String(
            String.UnicodeScalarView(
                collapsed.unicodeScalars.map { scalar in
                    (65...90).contains(scalar.value) ? Unicode.Scalar(scalar.value + 32)! : scalar
                }))
    }
}

public struct MediaAgreement: Sendable, Equatable {
    public enum Status: String, Sendable { case matched, confirmationRequired, ambiguous, missing }
    public let status: Status
    public let candidateIDs: [String]

    /// A weak or ambiguous candidate never authorizes automatic playback.
    public static func resolve(_ remote: MediaDescriptor, local: [MediaDescriptor]) throws -> Self {
        guard local.count <= 256, Set(local.map(\.mediaID)).count == local.count else {
            throw ContractRejection.malformed
        }
        var exact: [String] = []
        var candidates: [String] = []
        for candidate in local {
            let sameHash = remote.fullHashSha256 != nil && candidate.fullHashSha256 == remote.fullHashSha256
            if sameHash {
                guard candidate.fileSizeBytes == remote.fileSizeBytes,
                    candidate.durationMs == nil || remote.durationMs == nil || candidate.durationMs == remote.durationMs
                else { throw ContractRejection.malformed }
                if let duration = remote.durationMs, duration > 0, candidate.durationMs == duration {
                    exact.append(candidate.mediaID)
                }
            }
            if sameHash || candidate.titleKey == remote.titleKey { candidates.append(candidate.mediaID) }
        }
        if !exact.isEmpty {
            return Self(status: exact.count == 1 ? .matched : .ambiguous, candidateIDs: exact.sorted())
        }
        return Self(status: candidates.isEmpty ? .missing : .confirmationRequired, candidateIDs: candidates.sorted())
    }
}
