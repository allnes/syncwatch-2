import Foundation
import SyncWatchDesign
import SyncWatchDomain

/// One movie owns local track requests. Room state and Syncplay are not involved.
@MainActor final class LocalPlaybackTracks: ObservableObject {
    private enum Failure: Error { case timeout, unavailable }
    @Published private(set) var menu: SelectionMenuPresentation?
    private let player: any PlaybackTrackControlPort
    private let activeScope: @MainActor () -> PlaybackScope?
    private let sourceID = "tracks-" + UUID().uuidString
    private var revision: Int64 = 0
    private var work: Task<Void, Never>?
    private var closed = false

    init(player: any PlaybackTrackControlPort, scope: @escaping @MainActor () -> PlaybackScope?) {
        self.player = player
        self.activeScope = scope
    }
    /// Called before the watch is admitted or any controls are enabled.
    func applyInitial(_ preferences: LocalTrackPreferences) async throws {
        guard !closed, let scope = activeScope() else { throw Failure.unavailable }
        let audio =
            try preferences.audioNames == nil
            ? nil
            : preferences.resolve(try await player.tracks(subtitles: false, scope: scope), subtitles: false)
        let subtitles =
            try preferences.subtitleNames == nil
            ? nil
            : preferences.resolve(try await player.tracks(subtitles: true, scope: scope), subtitles: true)
        for (id, isSubtitle) in [(audio, false), (subtitles, true)] {
            guard let id else { continue }
            try Task.checkCancellation()
            guard !closed else { throw Failure.unavailable }
            try await acknowledge(id, subtitles: isSubtitle, scope: scope)
        }
    }
    private func acknowledge(_ id: Int32, subtitles: Bool, scope: PlaybackScope) async throws {
        if try await player.selectedTrack(subtitles: subtitles, scope: scope) == id { return }
        try await player.selectTrack(id, subtitles: subtitles, scope: scope)
        let deadline = ContinuousClock.now.advanced(by: .seconds(3))
        while try await player.selectedTrack(subtitles: subtitles, scope: scope) != id {
            try Task.checkCancellation()
            guard !closed, ContinuousClock.now < deadline else { throw Failure.timeout }
            try await Task.sleep(for: .milliseconds(20))
        }
    }
    func open(_ kind: String) {
        guard !closed, kind == "audio" || kind == "subtitles" else { return }
        dismiss()
        let revision = revision
        let previous = work
        work = Task {
            await previous?.value
            guard !Task.isCancelled else { return }
            do { publish(try await snapshot(kind, revision: revision), revision: revision) } catch {
                unavailable(kind, revision: revision)
            }
        }
    }
    func select(_ request: SelectionMenuRequest) {
        guard !closed, let current = menu, current.allows(request.entryID), request.scope == "local",
            request.kind == current.kind, request.sourceID == sourceID, request.revision == revision,
            request.action == current.definition?.action, let id = Int32(request.entryID)
        else { return }
        work?.cancel()
        revision += 1
        let revision = revision
        var pending = current
        pending.revision = revision
        pending.enabled = false
        menu = pending
        let previous = work
        work = Task {
            await previous?.value
            guard !Task.isCancelled else { return }
            do {
                let subtitles = request.kind == "subtitles"
                guard let scope = activeScope() else { throw Failure.unavailable }
                try await acknowledge(id, subtitles: subtitles, scope: scope)
                publish(try await snapshot(request.kind, revision: revision), revision: revision)
                if !closed, !Task.isCancelled, revision == self.revision { dismiss() }
            } catch { unavailable(request.kind, revision: revision) }
        }
    }
    private func snapshot(_ kind: String, revision: Int64) async throws -> SelectionMenuPresentation {
        guard let scope = activeScope() else { throw Failure.unavailable }
        let subtitles = kind == "subtitles"
        let tracks = try await player.tracks(subtitles: subtitles, scope: scope)
        let selected = try await player.selectedTrack(subtitles: subtitles, scope: scope)
        var result = SelectionMenuPresentation()
        result.kind = kind
        result.sourceID = sourceID
        result.revision = revision
        result.entries = tracks.map { SelectionMenuEntry(id: String($0.id), label: $0.name, disabledTrack: $0.id < 0) }
        if subtitles, !tracks.contains(where: { $0.id < 0 }) { result.entries.insert(.offTrack, at: 0) }
        result.selectedID = result.entries.contains { $0.id == String(selected) } ? String(selected) : nil
        result.enabled = true
        return result
    }
    private func publish(_ value: SelectionMenuPresentation, revision: Int64) {
        guard !closed, !Task.isCancelled, revision == self.revision else { return }
        menu = value
    }
    private func unavailable(_ kind: String, revision: Int64) {
        var value = SelectionMenuPresentation()
        value.kind = kind
        publish(value, revision: revision)
    }
    func dismiss() {
        revision += 1
        work?.cancel()
        menu = nil
    }
    func close() async {
        closed = true
        dismiss()
        await work?.value
        work = nil
    }
    func settled() async { await work?.value }
}
