import SwiftUI

/// Thin observation/event binding. The common document owns every visual decision.
public struct SelectionMenu: View {
    public var presentation: SelectionMenuPresentation
    public var language: String
    public var onSelection: (SelectionMenuRequest) -> Void
    public init(
        presentation: SelectionMenuPresentation = SelectionMenuPresentation(), language: String = "en",
        onSelection: @escaping (SelectionMenuRequest) -> Void = { _ in }
    ) {
        self.presentation = presentation
        self.language = language
        self.onSelection = onSelection
    }
    public var body: some View {
        DesignSurface("SelectionMenu", context: SelectionMenuBindings.context(presentation), language: language) { e in
            guard e.action == "selectEntry", let id = e.value, let token = e.payload else { return }
            presentation.dispatch(id, contextToken: token, to: onSelection)
        }
    }
}

enum SelectionMenuBindings {
    static func context(_ p: SelectionMenuPresentation) -> DesignContext {
        let entries = p.isValid ? p.entries : []
        return DesignContext(
            [
                "kind": p.kind, "menuLabel": p.definition?.label ?? "selectionUnavailable",
                "contextToken": p.contextToken, "entryCount": String(entries.count),
                "hasEntries": String(!entries.isEmpty),
                "emptyLabel": p.isValid ? "selectionEmpty" : "selectionUnavailable",
            ],
            collections: [
                "entries": entries.map {
                    DesignContext([
                        "id": $0.id, "label": $0.label, "selected": String(p.selectedID == $0.id),
                        "enabled": String(p.enabled && $0.enabled),
                    ])
                }
            ])
    }
}
