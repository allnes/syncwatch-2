import SwiftUI

public enum LibraryVisualState: String, CaseIterable, Sendable {
    case empty, scanning, selected, missingMedia, reconnecting
}

public struct LibraryEntry: Identifiable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let location: String

    public init(id: String, title: String, location: String) {
        self.id = id
        self.title = title
        self.location = location
    }
}

/// Presentation data only. Services supply entries and capabilities; rendering starts no provider or filesystem work.
public struct LibraryPresentation: Sendable {
    public var roomStatus = ""
    public var state: LibraryVisualState
    public var entries: [LibraryEntry]
    public var selectedID: String?
    public var enabledActions: Set<String>

    public init(
        state: LibraryVisualState = .empty, entries: [LibraryEntry] = [], selectedID: String? = nil,
        enabledActions: Set<String> = []
    ) {
        self.state = state
        self.entries = entries
        self.selectedID = selectedID
        self.enabledActions = enabledActions
    }

    public var selected: LibraryEntry? { entries.first { $0.id == selectedID } }

    public func allows(_ action: String) -> Bool {
        guard enabledActions.contains(action), SyncWatchCopy.libraryActions.contains(action) else { return false }
        if action == "startWatching" { return state == .selected && selected != nil }
        if action == "selectMovie" || action == "search" { return state != .scanning }
        return true
    }

    public func dispatch(_ action: String, value: String? = nil, to handler: (String, String?) -> Void) {
        guard allows(action) else { return }
        if action == "selectMovie", !entries.contains(where: { $0.id == value }) { return }
        handler(action, value)
    }

    public static func gallery(_ state: LibraryVisualState) -> LibraryPresentation {
        let entries =
            state == .empty || state == .scanning
            ? []
            : SyncWatchCopy.galleryMovies.enumerated().map {
                LibraryEntry(id: String($0.offset), title: $0.element, location: "Movies/" + $0.element)
            }
        return LibraryPresentation(
            state: state, entries: entries, selectedID: entries.first?.id,
            enabledActions: ["chooseFolder", "rescan", "search", "selectMovie", "startWatching", "openSettings"])
    }
}

public struct LibraryWorkspace: View {
    public var presentation: LibraryPresentation
    public var language: String
    public var onAction: (String, String?) -> Void
    @State private var query = ""
    public init(
        presentation: LibraryPresentation = LibraryPresentation(), language: String = "en",
        onAction: @escaping (String, String?) -> Void = { _, _ in }
    ) {
        self.presentation = presentation
        self.language = language
        self.onAction = onAction
    }
    public var body: some View {
        DesignSurface(
            "Library", context: DesignBindings.library(presentation, query: query, language: language),
            language: language
        ) { event in
            if event.action == "search" { query = event.value ?? "" }
            presentation.dispatch(event.action, value: event.value, to: onAction)
        }
    }
}
