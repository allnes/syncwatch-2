import SwiftUI

public enum PlayerSettingsVisualState: String, CaseIterable, Sendable {
    case editing, savedNotice, invalidConfiguration, readOnly
}

/// Draft only. Save publishes a snapshot after the application acknowledges the complete transaction.
public struct PlayerSettingsEditor: Sendable {
    public private(set) var values: [String: String]
    public let editableFields: Set<String>
    public let canSave: Bool
    public private(set) var state: PlayerSettingsVisualState
    public private(set) var message = ""
    private var original: [String: String]

    public init(
        values: [String: String] = [:], editableFields: Set<String> = [], canSave: Bool = false,
        state: PlayerSettingsVisualState = .editing
    ) {
        self.values = SyncWatchPlayerSettings.defaults.merging(values) { _, value in value }
        original = self.values
        self.editableFields = editableFields
        self.canSave = canSave && state != .readOnly
        self.state = self.canSave ? state : .readOnly
        if self.state == .invalidConfiguration { message = "invalidConfiguration" }
        if self.state == .savedNotice { message = "changesSaved" }
    }
    public func allows(_ id: String) -> Bool {
        canSave && editableFields.contains(id) && SyncWatchPlayerSettings.fields.contains { $0.id == id }
    }
    public mutating func edit(_ id: String, value: String) {
        guard allows(id) else { return }
        values[id] = value
        state = .editing
        message = ""
    }
    public static func valid(_ value: String, for field: PlayerSettingField) -> Bool {
        guard value.utf16.count <= 64,
            !value.unicodeScalars.contains(where: { $0.value < 32 || (127...159).contains($0.value) })
        else { return false }
        if field.kind == "boolean" { return ["true", "false"].contains(value) }
        if field.kind != "range" { return field.options.contains { $0.id == value } }
        guard value.range(of: #"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"#, options: .regularExpression) != nil,
            let number = Double(value), number.isFinite, (field.minimum...field.maximum).contains(number)
        else { return false }
        let ticks = (number - field.minimum) / field.step
        return abs(ticks - ticks.rounded()) < 1e-8
    }
    public var isValid: Bool {
        Set(values.keys) == Set(SyncWatchPlayerSettings.defaults.keys)
            && editableFields.isSubset(of: Set(SyncWatchPlayerSettings.defaults.keys))
            && SyncWatchPlayerSettings.fields.allSatisfy { Self.valid(values[$0.id] ?? "", for: $0) }
    }
    public func canReset(_ section: String) -> Bool {
        SyncWatchPlayerSettings.sections.contains(section)
            && SyncWatchPlayerSettings.fields.contains { $0.section == section && allows($0.id) }
    }
    public mutating func reset(_ section: String) {
        guard canReset(section) else { return }
        for field in SyncWatchPlayerSettings.fields where field.section == section && allows(field.id) {
            values[field.id] = SyncWatchPlayerSettings.defaults[field.id]
        }
        state = .editing
        message = ""
    }
    @discardableResult public mutating func save(using persist: ([String: String]) -> Bool) -> Bool {
        guard canSave else { return false }
        guard isValid else {
            state = .invalidConfiguration
            message = "invalidConfiguration"
            return false
        }
        guard persist(values) else {
            state = .invalidConfiguration
            message = "saveFailed"
            return false
        }
        original = values
        state = .savedNotice
        message = "changesSaved"
        return true
    }
    public mutating func cancel() {
        values = original
        state = canSave ? .editing : .readOnly
        message = ""
    }
    public static func canonical(_ number: Double) -> String {
        guard number.isFinite else { return "" }
        var value = String(format: "%.2f", locale: Locale(identifier: "en_US_POSIX"), abs(number) < 1e-8 ? 0 : number)
        while value.last == "0" { value.removeLast() }
        if value.last == "." { value.removeLast() }
        return value
    }
}

public struct PlayerSubtitlePreview: View {
    public var values: [String: String]
    public var language: String
    public init(values: [String: String], language: String = "en") {
        self.values = values
        self.language = language
    }
    public var body: some View {
        DesignSurface("subtitlePreview", context: DesignBindings.preview(values), language: language)
    }
}

public struct PlayerSettingsDialog: View {
    @Binding private var editor: PlayerSettingsEditor
    public var language: String
    public var onSave: ([String: String]) -> Bool
    public var onClose: () -> Void
    public var onMove: (CGSize) -> Void
    @State private var section: String
    @State private var lastDrag = CGSize.zero
    public init(
        editor: Binding<PlayerSettingsEditor>, language: String = "en", section: String = "playback",
        onSave: @escaping ([String: String]) -> Bool = { _ in false }, onClose: @escaping () -> Void = {},
        onMove: @escaping (CGSize) -> Void = { _ in }
    ) {
        _editor = editor
        self.language = language
        self.onSave = onSave
        self.onClose = onClose
        self.onMove = onMove
        _section = State(initialValue: SyncWatchPlayerSettings.sections.contains(section) ? section : "playback")
    }
    public var body: some View {
        DesignSurface(
            "PlayerSettings", context: DesignBindings.playerSettings(editor, section: section, language: language),
            language: language
        ) { event in
            switch event.action {
            case "selectSection":
                if let value = event.value, SyncWatchPlayerSettings.sections.contains(value) { section = value }
            case "editField":
                if let id = event.payload, let value = event.value {
                    if let field = SyncWatchPlayerSettings.fields.first(where: { $0.id == id }), field.kind == "range",
                        let number = Double(value)
                    {
                        editor.edit(
                            id,
                            value: PlayerSettingsEditor.canonical(
                                field.minimum + ((number - field.minimum) / field.step).rounded() * field.step))
                    } else {
                        editor.edit(id, value: value)
                    }
                }
            case "resetSection": editor.reset(section)
            case "save": editor.save(using: onSave)
            case "close", "cancel":
                editor.cancel()
                onClose()
            case "moveDialog":
                if let value = event.value {
                    let delta = value.split(separator: ",").compactMap { Double($0) }
                    if delta.count == 2 {
                        let current = CGSize(width: delta[0], height: delta[1])
                        onMove(CGSize(width: current.width - lastDrag.width, height: current.height - lastDrag.height))
                        lastDrag = current
                    }
                } else {
                    lastDrag = .zero
                }
            default: break
            }
        }
    }
}
