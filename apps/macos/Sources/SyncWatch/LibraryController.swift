import Foundation
import SwiftUI
import SyncWatchDesign
import SyncWatchLibrary

/// A local selection retains the OS folder grant independently of Library navigation or rescans.
/// Its path-based identifier is not evidence of a matching peer edition.
struct LibraryMediaSelection: Sendable {
    let media: LocalMediaFile
    let access: LibraryFolderAccess
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
    @Published var errorKey: String?
    private let scanner = FileSystemLibrary()
    private let persistence: LibraryRecordIO
    private var stable: LibraryPresentation?
    private var grant: LibraryFolderAccess?
    private var catalog: [String: LocalMediaFile] = [:]
    private var pending: Task<Void, Never>?
    private var generation = UUID()
    private var closed = false
    private let savedSelection: String?

    init(store: any LibraryAccessStore, selectedID: String? = nil) {
        persistence = LibraryRecordIO(store)
        savedSelection = selectedID
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
            stable = presentation
        }
    }
    func selectedMedia() -> LibraryMediaSelection? {
        guard !closed, presentation.state == .selected, let id = presentation.selectedID,
            let media = catalog[id], let grant
        else { return nil }
        return LibraryMediaSelection(media: media, access: grant)
    }
    func close() {
        closed = true
        generation = UUID()
        pending?.cancel()
        grant = nil
        catalog = [:]
        presentation.enabledActions = []
    }
    func settled() async { await pending?.value }

    private func run(_ acquire: @escaping @Sendable () async throws -> LibraryFolderAccess?) {
        guard !closed else { return }
        pending?.cancel()
        let token = UUID()
        generation = token
        let previous = stable ?? presentation
        stable = previous
        errorKey = nil
        presentation.state = .scanning
        pending = Task {
            do {
                guard let next = try await acquire() else {
                    if generation == token { presentation = previous }
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
                presentation = LibraryPresentation(
                    state: rows.isEmpty ? .empty : .selected, entries: rows, selectedID: selected,
                    enabledActions: ["chooseFolder", "rescan", "search", "selectMovie", "openSettings"])
                stable = presentation
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
                    errorKey = "libraryUnavailable"
                }
            }
        }
    }
}
