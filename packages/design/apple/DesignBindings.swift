import SwiftUI

/// Presentation facts and input translation only. Layout, typography and visual variants live in layouts.json.
enum DesignBindings {
    static func capabilities(_ actions: [String], allows: (String) -> Bool) -> [String: String] {
        Dictionary(uniqueKeysWithValues: actions.map { ("can." + $0, String(allows($0))) })
    }
    static func library(_ p: LibraryPresentation, query: String, language: String) -> DesignContext {
        var values = capabilities(SyncWatchCopy.libraryActions, allows: p.allows)
        values.merge([
            "namespace": "library", "query": query, "entryCount": String(p.entries.count),
            "filesLabel": SyncWatchCopy.text("files", language: language), "hasEntries": String(!p.entries.isEmpty),
            "hasSelection": String(p.selected != nil), "selectedTitle": p.selected?.title ?? "",
            "selectedLocation": p.selected?.location ?? "",
            "emptyMessage": p.state == .scanning ? "scanning" : "empty",
            "missingMedia": String(p.state == .missingMedia),
            "roomMessage": p.state == .reconnecting ? "reconnecting" : "disconnected",
        ]) { _, v in v }
        let entries = p.entries.filter { query.isEmpty || $0.title.localizedCaseInsensitiveContains(query) }.map {
            DesignContext(["id": $0.id, "title": $0.title, "selected": String($0.id == p.selectedID)])
        }
        return DesignContext(values, collections: ["entries": entries])
    }
    static func player(_ p: PlayerPresentation) -> DesignContext {
        var values = capabilities(SyncWatchPlayer.actions, allows: p.allows)
        values.merge([
            "namespace": "player", "title": p.title, "state": p.state.rawValue,
            "position": String(p.displayedPosition), "duration": String(p.displayedDuration),
            "positionText": PlayerPresentation.time(p.displayedPosition),
            "durationText": PlayerPresentation.time(p.displayedDuration),
            "volume": String(p.isValid ? p.volume : 0), "playIcon": p.playing ? "player.pause" : "player.play",
            "playLabel": p.playing ? "pause" : "play", "volumeIcon": p.muted ? "player.muted" : "player.volume",
            "volumeLabel": p.muted ? "unmuteMovie" : "muteMovie",
        ]) { _, v in v }
        return DesignContext(values)
    }
    static func settings(_ editor: SettingsEditor, section: String) -> DesignContext {
        let fields = SyncWatchSettings.fields.filter { $0.section == section }.map { field in
            let options = field.options.map { option in
                DesignContext(["id": option, "label": "option" + option.prefix(1).uppercased() + option.dropFirst()])
            }
            return DesignContext(
                [
                    "id": field.id, "label": field.label,
                    "kind": ["choice", "boolean"].contains(field.kind) ? field.kind : "text",
                    "value": editor.values[field.id] ?? "",
                    "editable": String(editor.editableFields.contains(field.id)), "isRange": "false",
                ], collections: ["options": options])
        }
        let status =
            !editor.canSave ? "settingsReadOnly" : editor.state == .savedNotice ? "changesSaved" : editor.message
        return DesignContext(
            [
                "namespace": "settings", "section": section, "dialogTitle": "openSettings", "status": status,
                "saved": String(editor.state == .savedNotice), "can.save": String(editor.canSave), "can.close": "true",
                "can.cancel": "true",
                "interfaceSection": String(section == "interface"),
                "unavailable": String(
                    !SyncWatchSettings.fields.contains {
                        $0.section == section && editor.editableFields.contains($0.id)
                    }),
            ], collections: ["sections": sections(SyncWatchSettings.sections, selected: section), "fields": fields])
    }
    static func playerSettings(_ editor: PlayerSettingsEditor, section: String, language: String) -> DesignContext {
        let fields = SyncWatchPlayerSettings.fields.filter { $0.section == section }
        let rows = Set(fields.map(\.row)).sorted().map { row in
            DesignContext(
                ["id": String(row)],
                collections: [
                    "fields": fields.filter { $0.row == row }.map { field in
                        let raw = editor.values[field.id] ?? ""
                        let safe =
                            PlayerSettingsEditor.valid(raw, for: field)
                            ? raw : SyncWatchPlayerSettings.defaults[field.id] ?? ""
                        let options = field.options.map { option in
                            DesignContext([
                                "id": option.id, "fieldID": field.id, "label": option.label,
                                "selected": String(option.id == raw),
                                "swatchColor": option.colorToken.map { "@" + $0 } ?? "",
                            ])
                        }
                        return DesignContext(
                            [
                                "id": field.id, "label": field.label, "kind": field.kind, "value": raw,
                                "number": safe, "minimum": String(field.minimum), "maximum": String(field.maximum),
                                "step": String(field.step),
                                "unitText": field.unit == "unitNone"
                                    ? "" : " " + SyncWatchCopy.text(field.unit, language: language),
                                "isRange": String(field.kind == "range"), "editable": String(editor.allows(field.id)),
                            ], collections: ["options": options])
                    }
                ])
        }
        var context = preview(editor.values)
        context.values.merge([
            "namespace": "playerSettings", "section": section, "dialogTitle": "playerSettings",
            "status": !editor.canSave ? "settingsReadOnly" : editor.message,
            "saved": String(editor.state == .savedNotice), "can.save": String(editor.canSave),
            "can.resetSection": String(editor.canReset(section)),
            "can.close": "true", "can.cancel": "true", "showSubtitle": String(section == "subtitles"),
        ]) { _, v in v }
        context.collections = ["sections": sections(SyncWatchPlayerSettings.sections, selected: section), "rows": rows]
        return context
    }
    static func preview(_ values: [String: String]) -> DesignContext {
        func setting(_ id: String) -> String {
            guard let field = SyncWatchPlayerSettings.fields.first(where: { $0.id == id }), let value = values[id],
                PlayerSettingsEditor.valid(value, for: field)
            else { return SyncWatchPlayerSettings.defaults[id] ?? "" }
            return value
        }
        var result = Dictionary(
            uniqueKeysWithValues: ["subtitleSize", "subtitlePadding", "subtitleOffset", "subtitleFont", "outlineWidth"]
                .map { ($0, setting($0)) })
        result["subtitleTop"] = String(setting("subtitlePosition") == "top")
        for (binding, id) in [("subtitleFill", "subtitleColor"), ("outlineFill", "outlineColor")] {
            let option = SyncWatchPlayerSettings.fields.first { $0.id == id }?.options.first { $0.id == setting(id) }
            result[binding] = option?.colorToken.map { "@" + $0 } ?? ""
        }
        return DesignContext(result)
    }
    private static func sections(_ source: [String], selected: String) -> [DesignContext] {
        source.map { DesignContext(["id": $0, "selected": String($0 == selected)]) }
    }
}
