import Foundation
import SwiftUI
import SyncWatchDesign
import SyncWatchLibrary

/// A local selection retains the OS folder grant independently of Library navigation or rescans.
/// Its path-based identifier is not evidence of a matching peer edition.
struct LibraryMediaSelection: Sendable {
    let media: LocalMediaFile
    let access: LibraryFolderAccess
    var tracks = LocalTrackPreferences()
}

private actor LibraryRecordIO {
    let store: any LibraryAccessStore
    init(_ store: any LibraryAccessStore) { self.store = store }
    func read() throws -> LibraryAccessRead {
        try Task.checkCancellation()
        return try store.read()
    }
    func write(_ record: LibraryAccessRecord) throws {
        try Task.checkCancellation()
        try store.write(record)
    }
}

/// Application state only; the common library owns rendering and action validation.
@MainActor final class LibraryController: ObservableObject {
    @Published private(set) var presentation = LibraryPresentation(enabledActions: ["chooseFolder", "openSettings"])
    @Published private(set) var tracks = LibraryTrackSelection()
    @Published var errorKey: String?
    @Published private(set) var roomRevision = UUID()
    var roomFiles: [LocalMediaFile] { catalog.values.sorted { $0.id < $1.id } }
    private let scanner = FileSystemLibrary(
        companionExtensions: Dictionary(
            uniqueKeysWithValues:
                SyncWatchSelectionMenu.externalFileFilters.flatMap { filter in
                    filter.extensions.map { ($0, filter.kind == "audio" ? LibraryCompanionKind.audio : .subtitles) }
                }))
    private var durations = LibraryDurationCache()
    private let persistence: LibraryRecordIO
    private var stable: LibraryPresentation?
    private var grant: LibraryFolderAccess?
    private var catalog: [String: LocalMediaFile] = [:]
    private var pending: Task<Void, Never>?
    private var generation = UUID()
    private var closed = false
    private let metadata: (any MediaMetadataReading)?
    private var metadataTask: Task<Void, Never>?
    private var metadataGeneration = UUID()
    private let savedSelection: String?

    init(store: any LibraryAccessStore, selectedID: String? = nil, metadata: (any MediaMetadataReading)? = nil) {
        persistence = LibraryRecordIO(store)
        savedSelection = selectedID
        self.metadata = metadata
    }
    func restore() {
        run { [persistence] in
            switch try await persistence.read() {
            case .loaded(let record): return try await Task.detached { try LibraryFolderAccess.restore(record) }.value
            case .missing, .invalid: return nil
            case .unsupportedVersion: throw LibraryAccessError.unsupportedVersion
            }
        }
    }
    func choose(_ url: URL) {
        run { try await Task.detached { try LibraryFolderAccess.selected(url) }.value }
    }
    func rescan() { if let grant { run { grant } } }
    func select(_ id: String) {
        guard !closed else { return }
        presentation.dispatch("selectMovie", value: id) { _, _ in
            presentation.selectedID = id
            startMetadata()
        }
    }
    func selectedMedia() -> LibraryMediaSelection? {
        guard !closed, presentation.state == .selected, let id = presentation.selectedID,
            let media = catalog[id], let grant
        else { return nil }
        return LibraryMediaSelection(media: media, access: grant, tracks: tracks.preferences)
    }
    func openTracks(_ kind: String, language: String) {
        guard !closed, presentation.allows(kind == "audio" ? "openLibraryAudio" : "openLibrarySubtitles") else {
            return
        }
        tracks.open(kind, language: language)
    }
    func selectTrack(_ request: SelectionMenuRequest) {
        guard !closed else { return }
        tracks.select(request)
        applyTrackSelection()
    }
    func dismissTracks() { tracks.dismiss() }
    private func applyTrackSelection() {
        presentation.metadataAudioName = tracks.audioName
        presentation.metadataSubtitleName = tracks.subtitleName
        presentation.metadataSubtitlesDisabled = tracks.subtitlesDisabled
        stable = presentation
    }
    func close() {
        closed = true
        tracks.reset()
        generation = UUID()
        pending?.cancel()
        metadataTask?.cancel()
        metadataGeneration = UUID()
        grant = nil
        catalog = [:]
        durations.clear()
        presentation.enabledActions = []
    }
    func settled() async { await pending?.value }
    func metadataSettled() async { await metadataTask?.value }
    func closeAndWait() async {
        close()
        await pending?.value
        await metadataTask?.value
        await metadata?.close()
    }

    private func cancelMetadata() {
        metadataGeneration = UUID()
        metadataTask?.cancel()
        tracks.reset()
        presentation.metadataAudioName = nil
        presentation.metadataSubtitleName = nil
        presentation.metadataSubtitlesDisabled = false
        presentation.metadataDurationMs = nil
        presentation.metadataWidth = 0
        presentation.metadataHeight = 0
        presentation.metadataAudioTracks = nil
        presentation.metadataSubtitleTracks = nil
        presentation.metadataLoading = false
        presentation.metadataUnavailable = false
    }
    private func publishDuration(_ value: Int64?, file: LocalMediaFile) {
        durations.record(value, for: file)
        presentation.entries = presentation.entries.map { row in
            row.id == file.id
                ? LibraryEntry(
                    id: row.id, title: row.title, location: row.location, durationMs: value,
                    folderMovie: row.folderMovie) : row
        }
    }
    private func startMetadata() {
        let previous = metadataTask
        cancelMetadata()
        stable = presentation
        guard let metadata, let selection = selectedMedia() else { return }
        let token = metadataGeneration
        // Selection has priority. One owner processes the remaining scan in display order.
        let files =
            [selection.media]
            + presentation.entries.compactMap { catalog[$0.id] }
            .filter { $0.id != selection.media.id }
        presentation.metadataLoading = true
        stable = presentation
        metadataTask = Task {
            defer { withExtendedLifetime(selection.access) {} }
            await previous?.value
            for file in files {
                guard !closed, metadataGeneration == token, !Task.isCancelled else { return }
                let selected = file.id == selection.media.id
                if !selected, durations.duration(for: file) != nil { continue }
                do {
                    let value = try await metadata.read(file)
                    try Task.checkCancellation()
                    guard !closed, metadataGeneration == token else { return }
                    publishDuration(value.durationMs, file: file)
                    if selected {
                        presentation.metadataDurationMs = value.durationMs
                        presentation.metadataWidth = value.width
                        presentation.metadataHeight = value.height
                        presentation.metadataAudioTracks =
                            value.audioTracks + file.companions.filter { $0.kind == .audio }.count
                        presentation.metadataSubtitleTracks =
                            value.subtitleTracks + file.companions.filter { $0.kind == .subtitles }.count
                        presentation.metadataLoading = false
                        tracks.reset(value, companions: file.companions)
                        presentation.enabledActions.formUnion(["openLibraryAudio", "openLibrarySubtitles"])
                        applyTrackSelection()
                    }
                    stable = presentation
                } catch is CancellationError { return } catch {
                    guard !closed, metadataGeneration == token else { return }
                    publishDuration(nil, file: file)
                    if selected {
                        presentation.metadataLoading = false
                        presentation.metadataUnavailable = true
                    }
                    stable = presentation
                }
            }
        }
    }

    private func run(_ acquire: @escaping @Sendable () async throws -> LibraryFolderAccess?) {
        guard !closed else { return }
        pending?.cancel()
        cancelMetadata()
        let token = UUID()
        generation = token
        let previous = stable ?? presentation
        stable = previous
        errorKey = nil
        presentation.state = .scanning
        pending = Task {
            do {
                guard let next = try await acquire() else {
                    if generation == token {
                        presentation = previous
                        startMetadata()
                    }
                    return
                }
                try Task.checkCancellation()
                let files = try await scanner.scan(
                    root: next.url, rootID: next.rootId, recursive: next.scanSubfolders)
                try Task.checkCancellation()
                guard generation == token, !closed else { return }
                let ordered = files.sorted { a, b in
                    let left = a.title.lowercased()
                    let right = b.title.lowercased()
                    return left == right
                        ? a.relativePath.utf8.lexicographicallyPrecedes(b.relativePath.utf8)
                        : left.utf8.lexicographicallyPrecedes(right.utf8)
                }
                durations.reconcile(files)
                let rows = ordered.map {
                    LibraryEntry(
                        id: $0.id, title: $0.title, location: $0.file.path, durationMs: durations.duration(for: $0),
                        folderMovie: $0.folderMovie)
                }
                let selected =
                    [previous.selectedID, savedSelection].compactMap { $0 }.first { id in rows.contains { $0.id == id }
                    } ?? rows.first?.id
                grant = next
                catalog = Dictionary(uniqueKeysWithValues: files.map { ($0.id, $0) })
                roomRevision = UUID()
                presentation = LibraryPresentation(
                    state: rows.isEmpty ? .empty : .selected, entries: rows, selectedID: selected,
                    enabledActions: ["chooseFolder", "rescan", "search", "selectMovie", "openSettings"])
                startMetadata()
                if let record = next.record {
                    do { try await persistence.write(record) } catch is CancellationError {} catch {
                        if generation == token { errorKey = "librarySaveFailed" }
                    }
                } else {
                    errorKey = "librarySaveFailed"
                }
            } catch is CancellationError {} catch {
                if generation == token, !closed {
                    presentation = previous
                    startMetadata()
                    errorKey = "libraryUnavailable"
                }
            }
        }
    }
}
