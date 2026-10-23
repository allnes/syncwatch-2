import SwiftUI

enum SelectionMenuFixtures {
    static func presentation(kind: String, state: String, language: String = "en") -> SelectionMenuPresentation {
        var p = SelectionMenuPresentation()
        p.kind = kind
        p.sourceID = "fixture-" + kind
        p.revision = 1
        p.enabled = state != "readOnly"
        let count = state == "empty" ? 0 : state == "longList" ? SyncWatchSelectionMenu.galleryEntryCount : 3
        p.entries = (0..<count).map { index in
            let key = state == "longList" ? "selectionFixtureLong" : p.definition?.label ?? "selectionFixtureLabel"
            return SelectionMenuEntry(
                id: "item\(index)", label: SyncWatchCopy.text(key, language: language) + " \(index + 1)",
                enabled: index != 2)
        }
        p.selectedID = p.entries.first?.id
        return p
    }
}

/// In-memory gallery. The common Gallery and selectionFixture trees own composition.
public struct SelectionMenuGallery: View {
    @State private var kind = "playlist"
    @State private var state = "available"
    @State private var language = "en"
    @State private var dark = true
    @State private var revision: Int64 = 1
    @State private var selectedID: String?
    @State private var lastAction = ""
    public init() {}
    private var presentation: SelectionMenuPresentation {
        var p = SelectionMenuFixtures.presentation(kind: kind, state: state, language: language)
        p.revision = revision
        if let selectedID, p.entries.contains(where: { $0.id == selectedID }) { p.selectedID = selectedID }
        return p
    }
    private func choice(_ id: String, _ value: String, _ options: [String]) -> DesignContext {
        DesignContext(
            [
                "id": id, "label": "gallery" + id.prefix(1).uppercased() + id.dropFirst(), "kind": "choice",
                "value": value, "editable": "true",
            ],
            collections: ["options": options.map { DesignContext(["id": $0, "label": $0]) }])
    }
    public var body: some View {
        let p = presentation
        let controls = [
            choice("kind", kind, SyncWatchSelectionMenu.kinds.map(\.id)),
            choice("state", state, SyncWatchSelectionMenu.states), choice("language", language, ["en", "ru"]),
            DesignContext([
                "id": "dark", "label": "galleryDark", "kind": "boolean", "value": String(dark), "editable": "true",
            ]),
        ]
        DesignSurface(
            "Gallery", context: DesignContext(["lastAction": lastAction], collections: ["galleryControls": controls]),
            language: language,
            slots: [
                "galleryContent": AnyView(
                    DesignSurface(
                        "selectionFixture", language: language,
                        slots: [
                            "selectionFixtureContent": AnyView(
                                SelectionMenu(presentation: p, language: language) { request in
                                    lastAction = request.scope + ":" + request.action
                                    selectedID = request.entryID
                                    revision += 1
                                })
                        ]))
            ]
        ) { e in
            guard e.action == "gallery", let id = e.payload, let value = e.value else { return }
            switch id {
            case "kind": kind = value
            case "state": state = value
            case "language": language = value
            case "dark": dark = value == "true"
            default: return
            }
            selectedID = nil
            revision += 1
        }.preferredColorScheme(dark ? .dark : .light)
    }
}
