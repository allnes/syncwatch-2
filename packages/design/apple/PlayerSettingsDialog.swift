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
    private func setting(_ id: String) -> String {
        guard let field = SyncWatchPlayerSettings.fields.first(where: { $0.id == id }),
            let value = values[id], PlayerSettingsEditor.valid(value, for: field)
        else { return SyncWatchPlayerSettings.defaults[id] ?? "" }
        return value
    }
    private func number(_ id: String) -> Double { Double(setting(id)) ?? 0 }
    public var body: some View {
        GeometryReader { geometry in
            let size = number("subtitleSize")
            let padding = number("subtitlePadding")
            let top = setting("subtitlePosition") == "top"
            let base = top ? padding + size / 2 : geometry.size.height - padding - size / 2
            let offset = number("subtitleOffset") / 120 * geometry.size.height * 0.34 * (top ? 1 : -1)
            let position = min(geometry.size.height - size / 2, max(size / 2, base + offset))
            let text = Text(SyncWatchCopy.text("subtitlePreview", language: language))
            let design: Font.Design =
                setting("subtitleFont") == "serif"
                ? .serif : setting("subtitleFont") == "monospace" ? .monospaced : .default
            ZStack {
                ForEach(0..<8, id: \.self) { index in
                    text.foregroundStyle(
                        SyncWatchPlayerSettings.color(setting("outlineColor"))
                            ?? SyncWatchTokens.colorSubtitleBlack
                    )
                    .offset(
                        x: cos(Double(index) * .pi / 4) * number("outlineWidth"),
                        y: sin(Double(index) * .pi / 4) * number("outlineWidth"))
                }
                text.foregroundStyle(
                    SyncWatchPlayerSettings.color(setting("subtitleColor"))
                        ?? SyncWatchTokens.colorSubtitleWhite)
            }
            .font(.system(size: size, weight: .bold, design: design)).multilineTextAlignment(.center).lineLimit(2)
            .frame(width: max(1, geometry.size.width - padding * 2))
            .position(x: geometry.size.width / 2, y: position)
        }
        .frame(height: SyncWatchTokens.layoutPlayerSettingsPreviewHeight)
        .background(SyncWatchTokens.colorSharedVideoSurface).clipped()
        .accessibilityLabel(SyncWatchCopy.text("subtitlePreview", language: language))
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
    @Environment(\.colorScheme) private var scheme
    private var theme: SyncWatchTheme { .resolve(scheme) }
    private func t(_ key: String) -> String { key.isEmpty ? "" : SyncWatchCopy.text(key, language: language) }
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
    private func close() {
        editor.cancel()
        onClose()
    }
    private func button(_ id: String, filled: Bool = false, enabled: Bool = true, action: @escaping () -> Void)
        -> some View
    {
        Button(t(id), action: action).buttonStyle(.plain)
            .padding(.horizontal, SyncWatchTokens.layoutSettingsCardPadding).frame(
                height: SyncWatchTokens.layoutSettingsControlHeight
            )
            .background(
                filled ? theme.accent : theme.surfaceRaised,
                in: RoundedRectangle(cornerRadius: SyncWatchTokens.controlButtonRadius)
            )
            .overlay(RoundedRectangle(cornerRadius: SyncWatchTokens.controlButtonRadius).stroke(theme.border))
            .foregroundStyle(filled ? SyncWatchTokens.colorDarkText : theme.text).disabled(!enabled).opacity(
                enabled ? 1 : 0.4
            )
            .accessibilityIdentifier("playerSettings." + id)
    }
    public var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(t("playerSettings")).font(.system(size: SyncWatchTokens.typeSettingsTitleSize, weight: .bold))
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading).contentShape(Rectangle())
                    .gesture(
                        DragGesture().onChanged { drag in
                            onMove(
                                CGSize(
                                    width: drag.translation.width - lastDrag.width,
                                    height: drag.translation.height - lastDrag.height))
                            lastDrag = drag.translation
                        }.onEnded { _ in lastDrag = .zero })
                button("close") { close() }.keyboardShortcut(.cancelAction)
            }.padding(.horizontal, SyncWatchTokens.layoutSettingsCardPadding)
                .frame(height: SyncWatchTokens.layoutSettingsHeaderHeight).background(theme.backgroundDeep)
            Divider().overlay(theme.border)
            HStack(spacing: 0) {
                VStack(spacing: SyncWatchTokens.controlBorderWidth) {
                    ForEach(SyncWatchPlayerSettings.sections, id: \.self) { id in
                        Button {
                            section = id
                        } label: {
                            Text(t(id)).frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal, SyncWatchTokens.layoutSettingsCardPadding)
                                .frame(height: SyncWatchTokens.layoutSettingsSidebarRowHeight)
                                .background(
                                    section == id ? theme.selection : .clear,
                                    in: RoundedRectangle(cornerRadius: SyncWatchTokens.controlFieldRadius))
                        }.buttonStyle(.plain).accessibilityIdentifier("playerSettings.section." + id)
                            .accessibilityAddTraits(section == id ? .isSelected : [])
                    }
                    Spacer(minLength: 0)
                }.padding(SyncWatchTokens.layoutSettingsCardPadding)
                    .frame(width: SyncWatchTokens.layoutPlayerSettingsSidebarWidth).background(theme.backgroundDeep)
                Divider().overlay(theme.border)
                ScrollView {
                    VStack(alignment: .leading, spacing: SyncWatchTokens.controlCompactGap) {
                        HStack {
                            Text(t(section)).font(.system(size: SyncWatchTokens.typeSettingsSectionSize, weight: .bold))
                            Spacer()
                            button("resetSection", enabled: editor.canReset(section)) { editor.reset(section) }
                        }
                        Text(t(section + "Hint")).foregroundStyle(theme.textSecondary)
                        VStack(alignment: .leading, spacing: SyncWatchTokens.controlCompactGap) {
                            ForEach(
                                Array(Set(SyncWatchPlayerSettings.fields.filter { $0.section == section }.map(\.row)))
                                    .sorted(), id: \.self
                            ) { row in
                                HStack(alignment: .top, spacing: SyncWatchTokens.controlCompactGap) {
                                    ForEach(
                                        SyncWatchPlayerSettings.fields.filter {
                                            $0.section == section && $0.row == row
                                        }, id: \.id
                                    ) { field in
                                        control(field).frame(maxWidth: .infinity, alignment: .leading)
                                    }
                                }
                            }
                            if section == "subtitles" {
                                PlayerSubtitlePreview(values: editor.values, language: language)
                            }
                        }.padding(SyncWatchTokens.layoutPlayerSettingsCardPadding)
                            .background(
                                theme.backgroundDeep.opacity(0.34),
                                in: RoundedRectangle(cornerRadius: SyncWatchTokens.layoutPlayerSettingsCardRadius)
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: SyncWatchTokens.layoutPlayerSettingsCardRadius).stroke(
                                    theme.border))
                    }.padding(SyncWatchTokens.layoutSettingsContentPadding)
                }
            }
            Divider().overlay(theme.border)
            HStack {
                Text(t(!editor.canSave ? "settingsReadOnly" : editor.message)).font(
                    .system(size: SyncWatchTokens.typeCaptionSize)
                )
                .foregroundStyle(editor.state == .savedNotice ? theme.success : theme.textSecondary)
                .accessibilityIdentifier("playerSettings.status")
                Spacer(minLength: SyncWatchTokens.controlCompactGap)
                button("cancel") { close() }
                button("save", filled: true, enabled: editor.canSave) { editor.save(using: onSave) }.keyboardShortcut(
                    .defaultAction)
            }.padding(.horizontal, SyncWatchTokens.layoutSettingsCardPadding).frame(
                height: SyncWatchTokens.layoutSettingsFooterHeight)
        }
        .font(.system(size: SyncWatchTokens.typeSettingsBodySize)).foregroundStyle(theme.text)
        .environment(\.locale, Locale(identifier: language))
        .frame(width: SyncWatchTokens.layoutSettingsWidth, height: SyncWatchTokens.layoutPlayerSettingsHeight)
        .background(theme.surface).clipShape(RoundedRectangle(cornerRadius: SyncWatchTokens.controlCompactDialogRadius))
        .overlay(RoundedRectangle(cornerRadius: SyncWatchTokens.controlCompactDialogRadius).stroke(theme.border))
    }
    @ViewBuilder private func control(_ field: PlayerSettingField) -> some View {
        let value = Binding(get: { editor.values[field.id] ?? "" }, set: { editor.edit(field.id, value: $0) })
        let enabled = editor.allows(field.id)
        let raw = value.wrappedValue
        let number =
            Double(
                PlayerSettingsEditor.valid(raw, for: field) ? raw : SyncWatchPlayerSettings.defaults[field.id] ?? "0")
            ?? field.minimum
        VStack(alignment: .leading, spacing: SyncWatchTokens.controlBorderWidth) {
            if field.kind == "boolean" {
                Toggle(
                    t(field.label),
                    isOn: Binding(
                        get: { value.wrappedValue == "true" }, set: { value.wrappedValue = $0 ? "true" : "false" })
                )
                .toggleStyle(SettingsToggleStyle(theme: theme))
            } else {
                HStack {
                    Text(t(field.label)).foregroundStyle(theme.textSecondary)
                    if field.kind == "range" {
                        Spacer(minLength: 0)
                        Text(value.wrappedValue + (field.unit == "unitNone" ? "" : " " + t(field.unit)))
                    }
                }
                if field.kind == "range" {
                    PlayerRange(
                        value: max(0, min(field.maximum - field.minimum, number - field.minimum)),
                        maximum: field.maximum - field.minimum,
                        label: t(field.label), enabled: enabled, step: field.step,
                        accessibilityText: value.wrappedValue, theme: theme
                    ) {
                        value.wrappedValue = PlayerSettingsEditor.canonical(
                            field.minimum + ($0 / field.step).rounded() * field.step)
                    }
                } else if field.kind == "color" {
                    HStack(spacing: SyncWatchTokens.controlCompactGap) {
                        ForEach(field.options, id: \.id) { option in
                            Button {
                                value.wrappedValue = option.id
                            } label: {
                                Circle().fill(SyncWatchPlayerSettings.color(option.id) ?? theme.text)
                                    .frame(
                                        width: SyncWatchTokens.layoutPlayerSettingsColorSize,
                                        height: SyncWatchTokens.layoutPlayerSettingsColorSize
                                    )
                                    .padding(SyncWatchTokens.controlBorderWidth * 2)
                                    .overlay(
                                        Circle().stroke(
                                            option.id == value.wrappedValue ? theme.accent : theme.border,
                                            lineWidth: SyncWatchTokens.controlBorderWidth * 2))
                            }.buttonStyle(.plain).accessibilityLabel(t(option.label)).accessibilityAddTraits(
                                option.id == value.wrappedValue ? .isSelected : [])
                        }
                    }
                } else {
                    Menu {
                        ForEach(field.options, id: \.id) { option in
                            Button(t(option.label)) { value.wrappedValue = option.id }
                        }
                    } label: {
                        Text(t(field.options.first { $0.id == value.wrappedValue }?.label ?? ""))
                    }
                    .menuStyle(.borderlessButton).menuIndicator(.hidden)
                    .frame(
                        maxWidth: .infinity, minHeight: SyncWatchTokens.layoutSettingsControlHeight, alignment: .leading
                    )
                    .padding(.horizontal, SyncWatchTokens.layoutSettingsCardPadding)
                    .background(theme.inputFill, in: RoundedRectangle(cornerRadius: SyncWatchTokens.controlFieldRadius))
                    .overlay(RoundedRectangle(cornerRadius: SyncWatchTokens.controlFieldRadius).stroke(theme.border))
                    .overlay(alignment: .trailing) {
                        SettingsChoiceMark().fill(theme.textSecondary).frame(width: 8, height: 4)
                            .padding(.trailing, SyncWatchTokens.layoutSettingsCardPadding).allowsHitTesting(false)
                    }.accessibilityLabel(t(field.label))
                }
            }
        }.disabled(!enabled).accessibilityIdentifier("playerSettings.field." + field.id)
    }
}

public struct PlayerSettingsGallery: View {
    @State private var section = "playback"
    @State private var language = "en"
    @State private var dark = true
    @State private var failSave = false
    @State private var state = PlayerSettingsVisualState.editing
    @State private var editor = PlayerSettingsEditor(
        editableFields: Set(SyncWatchPlayerSettings.defaults.keys), canSave: true)
    @State private var offset = CGSize.zero
    public init() {}
    public var body: some View {
        VStack {
            HStack {
                Picker("Section", selection: $section) {
                    ForEach(SyncWatchPlayerSettings.sections, id: \.self) { Text($0).tag($0) }
                }
                Picker("State", selection: $state) {
                    ForEach(PlayerSettingsVisualState.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                }
                Picker("Language", selection: $language) {
                    Text("English").tag("en")
                    Text("Русский").tag("ru")
                }
                Toggle("Dark", isOn: $dark)
                Toggle("Fail save", isOn: $failSave)
            }.padding(SyncWatchTokens.controlCompactGap)
            GeometryReader { geometry in
                PlayerSettingsDialog(
                    editor: $editor, language: language, section: section, onSave: { _ in !failSave },
                    onMove: { drag in
                        let maxX = max(0, (geometry.size.width - SyncWatchTokens.layoutSettingsWidth) / 2)
                        let maxY = max(0, (geometry.size.height - SyncWatchTokens.layoutPlayerSettingsHeight) / 2)
                        offset = CGSize(
                            width: min(maxX, max(-maxX, offset.width + drag.width)),
                            height: min(maxY, max(-maxY, offset.height + drag.height)))
                    }
                ).id(section).offset(offset).frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }.preferredColorScheme(dark ? .dark : .light)
            .onChange(of: state) { new in
                editor = PlayerSettingsEditor(
                    editableFields: new == .readOnly ? [] : Set(SyncWatchPlayerSettings.defaults.keys),
                    canSave: new != .readOnly, state: new)
            }
    }
}
