import Foundation
import SyncWatchDomain
import SyncWatchLibrary

/// Owns a cancellable preparation while retaining the selected folder grant.
@MainActor final class SharedMediaPreparation {
    private var pending: Task<MediaDescriptor, Error>?
    private var closed = false
    private var prepared: LoadedMediaVersion?

    func prepare(
        _ selection: LibraryMediaSelection, player: any PlaybackPort & LoadedMediaContentPort, scope: PlaybackScope
    ) async throws
        -> MediaDescriptor
    {
        guard !closed else { throw CancellationError() }
        try Task.checkCancellation()
        if let pending { return try await wait(pending) }
        let task = Task {
            defer { withExtendedLifetime(selection.access) {} }
            let before = try await player.observe(scope)
            guard before.status == .ready, before.seekable, let duration = before.durationMs, duration > 0 else {
                throw ContractRejection.malformed
            }
            let version = try await player.contentVersion(scope)
            guard version.sizeBytes == selection.media.sizeBytes else { throw ContractRejection.malformed }
            let digest = try await FileContentHasher().sha256(sizeBytes: version.sizeBytes) { offset, capacity in
                try await player.readContent(at: offset, capacity: capacity, scope: scope)
            }
            try Task.checkCancellation()
            let after = try await player.observe(scope)
            guard after.status == .ready, after.seekable, after.durationMs == duration,
                try await player.contentVersion(scope) == version
            else {
                throw ContractRejection.malformed
            }
            try Task.checkCancellation()
            prepared = version
            let title = MediaDescriptor.logicalTitle(selection.media.title)
            return try MediaDescriptor(
                mediaID: selection.media.id, title: title, titleKey: MediaDescriptor.normalizedTitleKey(title),
                fileSizeBytes: selection.media.sizeBytes, durationMs: duration, fullHashSha256: digest)
        }
        pending = task
        defer { pending = nil }
        return try await wait(task)
    }
    func validate(player: any LoadedMediaContentPort, scope: PlaybackScope) async throws {
        guard !closed, let prepared, prepared.scope == scope,
            try await player.contentVersion(scope) == prepared
        else { throw ContractRejection.malformed }
    }
    private func wait(_ task: Task<MediaDescriptor, Error>) async throws -> MediaDescriptor {
        try await withTaskCancellationHandler {
            try await task.value
        } onCancel: {
            task.cancel()
        }
    }
    func close() async {
        closed = true
        pending?.cancel()
        _ = await pending?.result
        prepared = nil
    }
}
