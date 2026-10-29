import Foundation
import SyncWatchDesign

/// Correlates local catalog choices with one current watch. Rendering remains in common Design.
@MainActor final class WatchPlaylist: ObservableObject {
    @Published private(set) var menu: SelectionMenuPresentation?
    private var snapshot = SelectionMenuPresentation()
    private let sourceID = "playlist-" + UUID().uuidString
    private var closed = false

    func update(entries: [SelectionMenuEntry], selectedID: String?, enabled: Bool) {
        guard !closed else { return }
        let selectedID = entries.contains { $0.id == selectedID } ? selectedID : nil
        guard snapshot.entries != entries || snapshot.selectedID != selectedID || snapshot.enabled != enabled else {
            return
        }
        guard snapshot.revision < SyncWatchSelectionMenu.maximumRevision else {
            close()
            return
        }
        snapshot.kind = "playlist"
        snapshot.sourceID = sourceID
        snapshot.revision += 1
        snapshot.entries = entries
        snapshot.selectedID = selectedID
        snapshot.enabled = enabled
        // A catalog/recovery transition invalidates every previously rendered request.
        menu = nil
    }
    func open() {
        guard !closed, snapshot.isValid else { return }
        menu = snapshot
    }
    func dismiss() { menu = nil }
    func close() {
        closed = true
        menu = nil
        snapshot = SelectionMenuPresentation()
    }
    func neighbor(_ direction: Int) -> String? {
        guard !closed, snapshot.isValid, snapshot.enabled, direction == -1 || direction == 1,
            let index = snapshot.entries.firstIndex(where: { $0.id == snapshot.selectedID })
        else { return nil }
        var next = index + direction
        while snapshot.entries.indices.contains(next) {
            let entry = snapshot.entries[next]
            if entry.enabled { return entry.id }
            next += direction
        }
        return nil
    }
    func selection(_ request: SelectionMenuRequest) -> String? {
        guard !closed, let menu, request.kind == snapshot.kind, request.scope == "shared",
            request.action == snapshot.definition?.action, request.sourceID == sourceID,
            request.revision == snapshot.revision, menu.contextToken == snapshot.contextToken,
            snapshot.allows(request.entryID)
        else { return nil }
        dismiss()
        return request.entryID
    }
    func presentation(_ source: PlayerPresentation) -> PlayerPresentation {
        var value = source
        value.enabledActions.subtract(["openPlaylist", "previousFile", "nextFile"])
        value.hasPrevious = neighbor(-1) != nil
        value.hasNext = neighbor(1) != nil
        if !closed, snapshot.isValid, !snapshot.entries.isEmpty {
            value.enabledActions.insert("openPlaylist")
        }
        if value.hasPrevious { value.enabledActions.insert("previousFile") }
        if value.hasNext { value.enabledActions.insert("nextFile") }
        return value
    }
}
