import Foundation
import SyncWatchDesign
import SyncWatchDomain
import SyncWatchLibrary

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
    private var choosingRevision: Int64?
    private let picker: (any ExternalTrackChoosing)?
    private var language = "en"
    private var externalFiles: [LocalFileAccess] = []
    private var aliases: [String: [Int32: String]] = [:]

    init(
        player: any PlaybackTrackControlPort, scope: @escaping @MainActor () -> PlaybackScope?,
        picker: (any ExternalTrackChoosing)? = nil
    ) {
        self.player = player
        self.activeScope = scope
        self.picker = picker
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
        let files = [(preferences.audioFile, false), (preferences.subtitleFile, true)]
        let prepared = try files.compactMap { file, subtitles -> (LocalCompanionFile, LocalFileAccess, Bool)? in
            guard let file else { return nil }
            guard file.kind == (subtitles ? .subtitles : .audio) else { throw Failure.unavailable }
            return (file, try file.open(), subtitles)
        }
        guard prepared.isEmpty || player is any PlaybackExternalTrackPort else { throw Failure.unavailable }
        // Retain every prepared grant before the first native borrower, including failed acknowledgements.
        externalFiles.append(contentsOf: prepared.map { $0.1 })
        for (id, isSubtitle) in [(audio, false), (subtitles, true)] {
            guard let id else { continue }
            try Task.checkCancellation()
            guard !closed else { throw Failure.unavailable }
            try await acknowledge(id, subtitles: isSubtitle, scope: scope)
        }
        for (file, access, isSubtitle) in prepared {
            try Task.checkCancellation()
            guard !closed, activeScope() == scope, let external = player as? any PlaybackExternalTrackPort else {
                throw Failure.unavailable
            }
            let previous = Set(try await player.tracks(subtitles: isSubtitle, scope: scope).map(\.id))
            try await external.attachTrack(access.file, subtitles: isSubtitle, scope: scope)
            let id = try await attachment(subtitles: isSubtitle, excluding: previous, scope: scope)
            aliases[isSubtitle ? "subtitles" : "audio", default: [:]][id] = file.file.lastPathComponent
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
    func open(_ kind: String, language: String = "en") {
        guard !closed, kind == "audio" || kind == "subtitles" else { return }
        dismiss()
        self.language = language
        let revision = revision
        let previous = work
        work = Task {
            await previous?.value
            guard !Task.isCancelled else { return }
            do { publish(try await snapshot(kind, revision: revision), revision: revision) } catch {
                await unavailable(kind, revision: revision)
            }
        }
    }
    func select(_ request: SelectionMenuRequest) {
        guard !closed, let current = menu, current.allows(request.entryID), request.scope == "local",
            request.kind == current.kind, request.sourceID == sourceID, request.revision == revision,
            request.action == current.definition?.action,
            request.entryID == SyncWatchSelectionMenu.externalFileID || Int32(request.entryID) != nil
        else { return }
        work?.cancel()
        revision += 1
        let revision = revision
        var pending = current
        pending.revision = revision
        pending.enabled = false
        if request.entryID == SyncWatchSelectionMenu.externalFileID {
            choosingRevision = revision
            menu = nil
        } else {
            menu = pending
        }
        let previous = work
        work = Task {
            await previous?.value
            guard !Task.isCancelled else { return }
            defer { if choosingRevision == revision { choosingRevision = nil } }
            do {
                let subtitles = request.kind == "subtitles"
                guard let scope = activeScope() else { throw Failure.unavailable }
                if request.entryID == SyncWatchSelectionMenu.externalFileID {
                    guard let picker, let external = player as? any PlaybackExternalTrackPort else {
                        throw Failure.unavailable
                    }
                    let file = try await picker.choose(kind: request.kind, language: language)
                    try Task.checkCancellation()
                    guard !closed, self.revision == revision, activeScope() == scope else { throw Failure.unavailable }
                    guard let file else {
                        publish(try await snapshot(request.kind, revision: revision), revision: revision)
                        return
                    }
                    // Native submission may have borrowed the grant even if acknowledgement later fails.
                    externalFiles.append(file)
                    let previous = Set(try await player.tracks(subtitles: subtitles, scope: scope).map(\.id))
                    try await external.attachTrack(file.file, subtitles: subtitles, scope: scope)
                    let id = try await attachment(subtitles: subtitles, excluding: previous, scope: scope)
                    aliases[request.kind, default: [:]][id] = file.file.lastPathComponent
                } else if let id = Int32(request.entryID) {
                    try await acknowledge(id, subtitles: subtitles, scope: scope)
                }
                publish(try await snapshot(request.kind, revision: revision), revision: revision)
                if !closed, !Task.isCancelled, revision == self.revision { dismiss() }
            } catch { await unavailable(request.kind, revision: revision) }
        }
    }
    private func attachment(subtitles: Bool, excluding previous: Set<Int32>, scope: PlaybackScope) async throws -> Int32
    {
        let deadline = ContinuousClock.now.advanced(by: .seconds(3))
        while true {
            try Task.checkCancellation()
            guard !closed, activeScope() == scope, ContinuousClock.now < deadline else { throw Failure.timeout }
            let id = try await player.selectedTrack(subtitles: subtitles, scope: scope)
            if id >= 0, !previous.contains(id),
                try await player.tracks(subtitles: subtitles, scope: scope).contains(where: { $0.id == id })
            {
                return id
            }
            try await Task.sleep(for: .milliseconds(20))
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
        result.entries = tracks.map {
            SelectionMenuEntry(
                id: String($0.id),
                label: SelectionMenuEntry.observedLabel(aliases[kind]?[$0.id] ?? $0.name, language: language),
                disabledTrack: $0.id < 0)
        }
        if subtitles, !tracks.contains(where: { $0.id < 0 }) { result.entries.insert(.offTrack, at: 0) }
        if picker != nil, player is any PlaybackExternalTrackPort,
            result.entries.count < SyncWatchSelectionMenu.maximumEntries,
            let entry = SelectionMenuEntry.externalFile(kind: kind, language: language)
        {
            result.entries.append(entry)
        }
        result.selectedID = result.entries.contains { $0.id == String(selected) } ? String(selected) : nil
        result.enabled = true
        return result
    }
    private func publish(_ value: SelectionMenuPresentation, revision: Int64) {
        guard !closed, !Task.isCancelled, revision == self.revision else { return }
        menu = value
    }
    private func unavailable(_ kind: String, revision: Int64) async {
        guard !closed, !Task.isCancelled, revision == self.revision else { return }
        guard picker != nil, player is any PlaybackExternalTrackPort else {
            var value = SelectionMenuPresentation()
            value.kind = kind
            publish(value, revision: revision)
            return
        }
        var value = (try? await snapshot(kind, revision: revision)) ?? SelectionMenuPresentation()
        value.kind = kind
        value.sourceID = sourceID
        value.revision = revision
        if value.entries.isEmpty, let entry = SelectionMenuEntry.externalFile(kind: kind, language: language) {
            value.entries = [entry]
        }
        value.entries.insert(.externalFileFailure(language: language), at: 0)
        value.enabled = true
        publish(value, revision: revision)
    }
    func dismiss() {
        revision += 1
        choosingRevision = nil
        work?.cancel()
        picker?.cancel()
        menu = nil
    }
    /// Closing the menu to hand input to the native chooser does not cancel that choice.
    func dismissMenu() { if choosingRevision == nil { dismiss() } }
    func close() async {
        closed = true
        dismiss()
        await work?.value
        work = nil
    }
    func settled() async { await work?.value }
    /// Called by the playback owner only after native close has joined every descriptor borrower.
    func releaseExternalAccess() {
        externalFiles.removeAll()
        aliases.removeAll()
    }
}
