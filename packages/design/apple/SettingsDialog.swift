import SwiftUI

public enum SettingsVisualState: String, CaseIterable, Sendable {
    case editing, savedNotice, invalidConfiguration
}

/// Local presentation draft. A successful persistence acknowledgement is required for saved feedback.
public struct SettingsEditor: Sendable {
    public private(set) var values: [String: String]
    public let editableFields: Set<String>
    public let canSave: Bool
    public private(set) var state: SettingsVisualState
    public private(set) var message = ""
    private var original: [String: String]

    public init(
        values: [String: String] = [:], editableFields: Set<String> = [], canSave: Bool = false,
        state: SettingsVisualState = .editing
    ) {
        self.values = SyncWatchSettings.defaults.merging(values) { _, value in value }
        original = self.values
        self.editableFields = editableFields
        self.canSave = canSave
        self.state = state
        if state == .invalidConfiguration { message = "invalidConfiguration" }
    }

    public mutating func edit(_ id: String, value: String) {
        guard editableFields.contains(id), SyncWatchSettings.fields.contains(where: { $0.id == id }) else { return }
        values[id] = value
        state = .editing
        message = ""
    }

    public var isValid: Bool {
        guard Set(values.keys) == Set(SyncWatchSettings.defaults.keys),
            editableFields.isSubset(of: Set(SyncWatchSettings.defaults.keys))
        else { return false }
        return SyncWatchSettings.fields.allSatisfy { field in
            guard let value = values[field.id], value.utf16.count <= field.maxLength,
                !value.unicodeScalars.contains(where: { $0.value < 32 || (127...159).contains($0.value) })
            else { return false }
            if field.kind == "choice" { return field.options.contains(value) }
            if field.kind == "boolean" { return ["true", "false"].contains(value) }
            return true
        }
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
        state = .editing
        message = ""
    }
}

public struct SettingsDialog: View {
    @Binding private var editor: SettingsEditor
    public var language: String
    public var onSave: ([String: String]) -> Bool
    public var onClose: () -> Void
    @State private var section: String
    @Environment(\.colorScheme) private var colorScheme

    public init(
        editor: Binding<SettingsEditor>, language: String = "en", section: String = "interface",
        onSave: @escaping ([String: String]) -> Bool = { _ in false }, onClose: @escaping () -> Void = {}
    ) {
        _editor = editor
        self.language = language
        self.onSave = onSave
        self.onClose = onClose
        _section = State(initialValue: SyncWatchSettings.sections.contains(section) ? section : "interface")
    }

    private var theme: SyncWatchTheme { .resolve(colorScheme) }
    private func text(_ key: String) -> String { SyncWatchCopy.text(key, language: language) }

    public var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(text("brand") + " · " + text("openSettings"))
                    .font(.system(size: SyncWatchTokens.typeSettingsTitleSize, weight: .bold))
                Spacer()
                compactButton("close") { cancel() }.keyboardShortcut(.cancelAction)
            }
            .padding(.horizontal, SyncWatchTokens.layoutSettingsCardPadding)
            .frame(height: SyncWatchTokens.layoutSettingsHeaderHeight)
            .background(theme.backgroundDeep)
            Divider().overlay(theme.border)
            HStack(spacing: 0) {
                VStack(alignment: .leading, spacing: SyncWatchTokens.controlBorderWidth) {
                    ForEach(SyncWatchSettings.sections, id: \.self) { id in
                        Button {
                            section = id
                        } label: {
                            Text(text(id)).frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal, SyncWatchTokens.layoutSettingsCardPadding)
                                .frame(height: SyncWatchTokens.layoutSettingsSidebarRowHeight)
                                .background(
                                    section == id ? theme.selection : .clear,
                                    in: RoundedRectangle(cornerRadius: SyncWatchTokens.controlFieldRadius))
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("settings.section." + id)
                        .accessibilityAddTraits(section == id ? .isSelected : [])
                    }
                    Spacer(minLength: 0)
                }
                .padding(SyncWatchTokens.layoutSettingsCardPadding)
                .frame(width: SyncWatchTokens.layoutSettingsSidebarWidth)
                .background(theme.backgroundDeep)
                Divider().overlay(theme.border)
                ScrollView {
                    VStack(alignment: .leading, spacing: SyncWatchTokens.controlCompactGap) {
                        Text(text(section)).font(.system(size: SyncWatchTokens.typeSettingsSectionSize, weight: .bold))
                        Text(text(section + "Hint")).foregroundStyle(theme.textSecondary)
                        ForEach(SyncWatchSettings.fields.filter { $0.section == section }, id: \.id) { field in
                            setting(field)
                        }
                        if !SyncWatchSettings.fields.filter({ $0.section == section }).contains(where: {
                            editor.editableFields.contains($0.id)
                        }) {
                            Text(text("settingsUnavailable")).foregroundStyle(theme.textSecondary)
                        }
                    }
                    .padding(SyncWatchTokens.layoutSettingsContentPadding)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            Divider().overlay(theme.border)
            HStack {
                Text(text(statusKey)).font(.system(size: SyncWatchTokens.typeCaptionSize))
                    .foregroundStyle(editor.state == .savedNotice ? theme.success : theme.textSecondary)
                    .accessibilityIdentifier("settings.status")
                Spacer(minLength: SyncWatchTokens.controlCompactGap)
                compactButton("cancel") { cancel() }
                compactButton("save", filled: true, enabled: editor.canSave) { editor.save(using: onSave) }
                    .disabled(!editor.canSave).keyboardShortcut(.defaultAction)
            }
            .padding(.horizontal, SyncWatchTokens.layoutSettingsCardPadding)
            .frame(height: SyncWatchTokens.layoutSettingsFooterHeight)
        }
        .environment(\.locale, Locale(identifier: language))
        .font(.system(size: SyncWatchTokens.typeSettingsBodySize))
        .foregroundStyle(theme.text)
        .frame(width: SyncWatchTokens.layoutSettingsWidth, height: SyncWatchTokens.layoutSettingsHeight)
        .background(theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: SyncWatchTokens.controlCompactDialogRadius))
        .overlay(RoundedRectangle(cornerRadius: SyncWatchTokens.controlCompactDialogRadius).stroke(theme.border))
    }

    private var statusKey: String {
        if !editor.canSave { return "settingsReadOnly" }
        if editor.state == .savedNotice { return "changesSaved" }
        return editor.message
    }

    @ViewBuilder private func setting(_ field: SyncWatchSettingsField) -> some View {
        let value = Binding<String>(get: { editor.values[field.id] ?? "" }, set: { editor.edit(field.id, value: $0) })
        let enabled = editor.editableFields.contains(field.id)
        VStack(alignment: .leading, spacing: SyncWatchTokens.controlBorderWidth) {
            if field.kind == "boolean" {
                Toggle(
                    text(field.label),
                    isOn: Binding(
                        get: { value.wrappedValue == "true" },
                        set: {
                            value.wrappedValue = $0 ? "true" : "false"
                        })
                ).toggleStyle(SettingsToggleStyle(theme: theme))
            } else {
                Text(text(field.label)).foregroundStyle(theme.textSecondary)
                if field.kind == "choice" {
                    Menu {
                        ForEach(field.options, id: \.self) { option in
                            Button(text("option" + option.prefix(1).uppercased() + option.dropFirst())) {
                                value.wrappedValue = option
                            }
                        }
                    } label: {
                        Text(
                            text("option" + value.wrappedValue.prefix(1).uppercased() + value.wrappedValue.dropFirst()))
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
                    }
                    .accessibilityLabel(text(field.label))
                } else {
                    TextField(text(field.label), text: value).textFieldStyle(.plain)
                        .padding(.horizontal, SyncWatchTokens.layoutSettingsCardPadding)
                        .frame(height: SyncWatchTokens.layoutSettingsControlHeight)
                        .background(
                            theme.inputFill, in: RoundedRectangle(cornerRadius: SyncWatchTokens.controlFieldRadius)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: SyncWatchTokens.controlFieldRadius).stroke(theme.border))
                }
            }
        }
        .disabled(!enabled)
        .accessibilityIdentifier("settings.field." + field.id)
        .frame(
            maxWidth: field.section == "interface"
                ? SyncWatchTokens.layoutSettingsInterfaceFieldWidth : SyncWatchTokens.layoutSettingsFieldWidth,
            alignment: .leading)
    }

    private func compactButton(_ id: String, filled: Bool = false, enabled: Bool = true, action: @escaping () -> Void)
        -> some View
    {
        Button(text(id), action: action).buttonStyle(.plain)
            .padding(.horizontal, SyncWatchTokens.layoutSettingsCardPadding)
            .frame(height: SyncWatchTokens.layoutSettingsControlHeight)
            .foregroundStyle(filled ? SyncWatchTokens.colorDarkText : theme.text)
            .background(
                filled ? theme.accent : theme.surfaceRaised,
                in: RoundedRectangle(cornerRadius: SyncWatchTokens.controlButtonRadius)
            )
            .overlay(RoundedRectangle(cornerRadius: SyncWatchTokens.controlButtonRadius).stroke(theme.border))
            .disabled(!enabled).opacity(enabled ? 1 : 0.4)
            .accessibilityIdentifier("settings." + id)
    }

    private func cancel() {
        editor.cancel()
        onClose()
    }
}

public struct SettingsGallery: View {
    @State private var section = "interface"
    @State private var language = "en"
    @State private var dark = true
    @State private var state = SettingsVisualState.editing
    @State private var failSave = false
    @State private var editor = SettingsEditor(
        editableFields: Set(SyncWatchSettings.defaults.keys), canSave: true)

    public init() {}

    public var body: some View {
        VStack {
            HStack {
                Picker("State", selection: $state) {
                    ForEach(SettingsVisualState.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                }
                Picker("Section", selection: $section) {
                    ForEach(SyncWatchSettings.sections, id: \.self) { Text($0).tag($0) }
                }
                Picker("Language", selection: $language) {
                    Text("English").tag("en")
                    Text("Русский").tag("ru")
                }
                Toggle("Dark", isOn: $dark)
                Toggle("Fail save", isOn: $failSave)
            }.padding(SyncWatchTokens.layoutPanelPadding)
            Spacer()
            SettingsDialog(editor: $editor, language: language, section: section, onSave: { _ in !failSave })
                .id(section)
            Spacer()
        }
        .background(dark ? SyncWatchTheme.dark.background : SyncWatchTheme.light.background)
        .preferredColorScheme(dark ? .dark : .light)
        .onChange(of: state) { value in
            editor = SettingsEditor(editableFields: Set(SyncWatchSettings.defaults.keys), canSave: true, state: value)
        }
    }
}

struct SettingsChoiceMark: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: .zero)
        path.addLine(to: CGPoint(x: rect.width, y: 0))
        path.addLine(to: CGPoint(x: rect.midX, y: rect.height))
        path.closeSubpath()
        return path
    }
}

struct SettingsToggleStyle: ToggleStyle {
    var theme: SyncWatchTheme
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        Button {
            configuration.isOn.toggle()
        } label: {
            HStack {
                configuration.label
                Spacer()
                RoundedRectangle(cornerRadius: SyncWatchTokens.controlSettingsToggleHeight / 2)
                    .fill(configuration.isOn ? theme.accent : theme.border)
                    .frame(
                        width: SyncWatchTokens.controlSettingsToggleWidth,
                        height: SyncWatchTokens.controlSettingsToggleHeight
                    )
                    .overlay(alignment: configuration.isOn ? .trailing : .leading) {
                        Circle().fill(SyncWatchTokens.colorDarkText)
                            .frame(
                                width: SyncWatchTokens.controlSettingsToggleThumb,
                                height: SyncWatchTokens.controlSettingsToggleThumb
                            )
                            .padding(.horizontal, SyncWatchTokens.controlSettingsToggleInset)
                    }
            }
            .frame(minHeight: SyncWatchTokens.layoutSettingsControlHeight)
            .contentShape(Rectangle())
        }.buttonStyle(.plain).opacity(enabled ? 1 : 0.4)
    }
}
