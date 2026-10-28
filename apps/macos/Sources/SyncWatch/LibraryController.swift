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
    private let scanner = FileSystemLibrary()
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
    private func startMetadata() {
        let previous = metadataTask
        cancelMetadata()
        stable = presentation
        guard let metadata, let selection = selectedMedia() else { return }
        let token = metadataGeneration
        presentation.metadataLoading = true
        stable = presentation
        metadataTask = Task {
            // Keep the security-scoped folder alive until native input cleanup has completed.
            defer { withExtendedLifetime(selection.access) {} }
            await previous?.value
            do {
                try Task.checkCancellation()
                let value = try await metadata.read(selection.media)
                try Task.checkCancellation()
                guard !closed, metadataGeneration == token else { return }
                presentation.metadataDurationMs = value.durationMs
                presentation.metadataWidth = value.width
                presentation.metadataHeight = value.height
                presentation.metadataAudioTracks = value.audioTracks
                presentation.metadataSubtitleTracks = value.subtitleTracks
                presentation.metadataLoading = false
                tracks.reset(value)
                presentation.enabledActions.formUnion(["openLibraryAudio", "openLibrarySubtitles"])
                applyTrackSelection()
            } catch is CancellationError {} catch {
                guard !closed, metadataGeneration == token else { return }
                presentation.metadataLoading = false
                presentation.metadataUnavailable = true
                stable = presentation
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
                let rows = ordered.map { LibraryEntry(id: $0.id, title: $0.title, location: $0.file.path) }
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
