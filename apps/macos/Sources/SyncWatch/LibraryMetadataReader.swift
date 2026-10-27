import Foundation
import SyncWatchDomain
import SyncWatchLibrary
import SyncWatchPlayback

/// One silent, paused VLC owner for local selected-file inspection. It never joins a watch session.
actor LibraryMetadataReader: MediaMetadataReading {
    private let media: MediaConfiguration
    private let player = VLCPlayback()
    private let runID = "metadata-" + UUID().uuidString.lowercased()
    private var generation: UInt64 = 0
    private var opened = false
    private var active = false
    private var closed = false

    init(media: MediaConfiguration) { self.media = media }

    func read(_ file: LocalMediaFile) async throws -> MediaMetadata {
        guard !closed, !active else { throw MediaMetadataFailure.unavailable }
        active = true
        defer { active = false }
        generation += 1
        let scope = try PlaybackScope(clientRunID: runID, mediaGeneration: generation)
        do {
            try Task.checkCancellation()
            if !opened {
                try await player.open(package: media.package)
                opened = true
            }
            try Task.checkCancellation()
            try await player.load(file.file, scope: scope)
            let version = try await player.contentVersion(scope)
            guard version.sizeBytes == file.sizeBytes else { throw MediaMetadataFailure.changed }
            let clock = ContinuousClock()
            let deadline = clock.now.advanced(by: .seconds(3))
            var result: MediaMetadata?
            while clock.now < deadline {
                try Task.checkCancellation()
                let observation = try await player.observe(scope)
                if observation.status == .failed { throw MediaMetadataFailure.unavailable }
                if observation.status == .ready, !observation.buffering {
                    let audio = try await player.tracks(subtitles: false, scope: scope).filter { $0.id >= 0 }
                    let subtitles = try await player.tracks(subtitles: true, scope: scope).filter { $0.id >= 0 }
                    result = try MediaMetadata(
                        durationMs: observation.durationMs, width: observation.width, height: observation.height,
                        audioTracks: audio.count, subtitleTracks: subtitles.count)
                    if observation.durationMs != nil, observation.width > 0, observation.height > 0 { break }
                }
                try await Task.sleep(for: .milliseconds(50))
            }
            guard let result else { throw MediaMetadataFailure.unavailable }
            guard try await player.contentVersion(scope) == version else { throw MediaMetadataFailure.changed }
            let currentURL = URL(fileURLWithPath: file.file.path)
            let values = try currentURL.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
            guard values.fileSize.map(Int64.init) == file.sizeBytes,
                values.contentModificationDate == file.modificationDate
            else { throw MediaMetadataFailure.changed }
            await release(scope)
            return result
        } catch {
            await release(scope)
            throw error
        }
    }

    private func release(_ scope: PlaybackScope) async {
        let player = player
        await Task.detached { try? await player.stop(scope) }.value
    }

    func close() async {
        closed = true
        await player.close()
    }
}
