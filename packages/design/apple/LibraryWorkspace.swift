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

public struct SyncWatchButtonStyle: ButtonStyle {
    public var theme: SyncWatchTheme
    public var filled = false
    @Environment(\.isEnabled) private var enabled

    public init(theme: SyncWatchTheme, filled: Bool = false) {
        self.theme = theme
        self.filled = filled
    }

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: SyncWatchTokens.typeBodySize, weight: .semibold))
            .padding(.horizontal, SyncWatchTokens.layoutPanelPadding)
            .frame(
                minHeight: filled
                    ? SyncWatchTokens.controlFilledButtonMinHeight : SyncWatchTokens.controlOutlinedButtonMinHeight
            )
            .foregroundStyle(filled ? SyncWatchTokens.colorDarkText : theme.text)
            .background(
                filled ? theme.accent : theme.surfaceRaised,
                in: RoundedRectangle(cornerRadius: SyncWatchTokens.controlButtonRadius)
            )
            .overlay(
                RoundedRectangle(cornerRadius: SyncWatchTokens.controlButtonRadius).stroke(
                    filled ? theme.accent : theme.border)
            )
            .opacity(enabled ? (configuration.isPressed ? 0.75 : 1) : 0.4)
            .contentShape(RoundedRectangle(cornerRadius: SyncWatchTokens.controlButtonRadius))
    }
}

public struct SyncWatchPanel<Content: View>: View {
    public var theme: SyncWatchTheme
    private let content: Content

    public init(theme: SyncWatchTheme, @ViewBuilder content: () -> Content) {
        self.theme = theme
        self.content = content()
    }

    public var body: some View {
        content
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .background(theme.surface, in: RoundedRectangle(cornerRadius: SyncWatchTokens.layoutPanelRadius))
            .overlay(
                RoundedRectangle(cornerRadius: SyncWatchTokens.layoutPanelRadius).stroke(
                    theme.border, lineWidth: SyncWatchTokens.controlBorderWidth))
    }
}

public struct LibraryWorkspace: View {
    public var presentation: LibraryPresentation
    public var language: String
    public var onAction: (String, String?) -> Void
    @Environment(\.colorScheme) private var colorScheme
    @State private var query = ""

    public init(
        presentation: LibraryPresentation = LibraryPresentation(), language: String = "en",
        onAction: @escaping (String, String?) -> Void = { _, _ in }
    ) {
        self.presentation = presentation
        self.language = language
        self.onAction = onAction
    }

    private var theme: SyncWatchTheme { .resolve(colorScheme) }
    private func text(_ key: String) -> String { SyncWatchCopy.text(key, language: language) }
    private func emit(_ action: String, _ value: String? = nil) {
        presentation.dispatch(action, value: value, to: onAction)
    }

    public var body: some View {
        VStack(spacing: SyncWatchTokens.layoutPanelGap) {
            header
                .frame(height: SyncWatchTokens.layoutHeaderHeight)
            GeometryReader { geometry in
                HStack(alignment: .top, spacing: SyncWatchTokens.layoutPanelGap) {
                    library.frame(width: SyncWatchTokens.layoutLibraryPanelWidth)
                    VStack(spacing: SyncWatchTokens.layoutPanelGap) {
                        details.frame(
                            height: min(
                                SyncWatchTokens.layoutSelectedPanelMaxHeight,
                                max(
                                    SyncWatchTokens.layoutSelectedPanelMinHeight,
                                    geometry.size.height - SyncWatchTokens.layoutLowerPanelMinHeight
                                        - SyncWatchTokens.layoutPanelGap)))
                        HStack(spacing: SyncWatchTokens.layoutPanelGap) {
                            information(
                                "roomStatus",
                                message: presentation.state == .reconnecting ? "reconnecting" : "disconnected")
                            information("recentActivity", message: "noActivity")
                        }
                    }
                }
            }
        }
        .padding(SyncWatchTokens.layoutWorkspacePadding)
        .frame(minWidth: SyncWatchTokens.layoutMinimumWidth, minHeight: SyncWatchTokens.layoutMinimumHeight)
        .font(.system(size: SyncWatchTokens.typeBodySize))
        .foregroundStyle(theme.text)
        .background(
            LinearGradient(
                colors: [theme.gradientStart, theme.background, theme.backgroundDeep], startPoint: .topLeading,
                endPoint: .bottomTrailing))
    }

    private var header: some View {
        SyncWatchPanel(theme: theme) {
            HStack(spacing: SyncWatchTokens.layoutPanelGap) {
                PlayMark()
                    .frame(width: SyncWatchTokens.controlIconSize, height: SyncWatchTokens.controlIconSize)
                    .frame(width: SyncWatchTokens.controlBrandSize, height: SyncWatchTokens.controlBrandSize)
                    .foregroundStyle(SyncWatchTokens.colorDarkText)
                    .background(theme.accent, in: RoundedRectangle(cornerRadius: SyncWatchTokens.controlButtonRadius))
                    .accessibilityHidden(true)
                Text(text("brand")).font(.system(size: SyncWatchTokens.typeBrandSize, weight: .heavy))
                Divider().overlay(theme.border).padding(.vertical, SyncWatchTokens.layoutPanelPadding)
                Text(text("room")).lineLimit(1)
                Spacer(minLength: 0)
                ViewThatFits(in: .horizontal) {
                    HStack {
                        Text(text("friendOffline"))
                        Text(text("callInactive"))
                    }.fixedSize()
                    Text(text("callInactive")).fixedSize()
                    Color.clear.frame(width: 0)
                }.foregroundStyle(theme.textSecondary)
                action("openSettings", title: "openSettings")
            }
            .padding(.horizontal, SyncWatchTokens.layoutWorkspacePadding)
            .frame(maxHeight: .infinity)
        }
    }

    private var library: some View {
        SyncWatchPanel(theme: theme) {
            VStack(alignment: .leading, spacing: SyncWatchTokens.layoutPanelGap) {
                HStack {
                    Text(text("library")).font(.system(size: SyncWatchTokens.typeSectionSize, weight: .bold))
                    Spacer()
                    Text("\(presentation.entries.count) \(text("files"))").foregroundStyle(theme.textSecondary)
                }
                HStack {
                    action("chooseFolder", title: "chooseFolder")
                    action("rescan", title: "rescan")
                }
                TextField(text("search"), text: $query)
                    .textFieldStyle(.plain)
                    .padding(.horizontal, SyncWatchTokens.layoutPanelPadding)
                    .frame(height: SyncWatchTokens.controlFieldHeight)
                    .background(theme.inputFill, in: RoundedRectangle(cornerRadius: SyncWatchTokens.controlFieldRadius))
                    .overlay(RoundedRectangle(cornerRadius: SyncWatchTokens.controlFieldRadius).stroke(theme.border))
                    .disabled(!presentation.allows("search"))
                    .onChange(of: query) { value in emit("search", value) }
                    .accessibilityIdentifier("library.search")
                if presentation.entries.isEmpty {
                    Spacer()
                    Text(text(presentation.state == .scanning ? "scanning" : "empty"))
                        .foregroundStyle(theme.textSecondary).frame(maxWidth: .infinity)
                    Spacer()
                } else {
                    ScrollView {
                        VStack(spacing: SyncWatchTokens.controlCompactGap) {
                            ForEach(
                                presentation.entries.filter {
                                    query.isEmpty || $0.title.localizedCaseInsensitiveContains(query)
                                }
                            ) { entry in
                                Button {
                                    emit("selectMovie", entry.id)
                                } label: {
                                    HStack {
                                        Text(entry.title).lineLimit(2).multilineTextAlignment(.leading)
                                        Spacer(minLength: 0)
                                    }
                                    .padding(SyncWatchTokens.layoutPanelPadding)
                                    .frame(minHeight: SyncWatchTokens.controlRowMinHeight)
                                    .background(
                                        entry.id == presentation.selectedID
                                            ? theme.selection : theme.surfaceRaised,
                                        in: RoundedRectangle(cornerRadius: SyncWatchTokens.controlRowRadius))
                                }
                                .buttonStyle(.plain).disabled(!presentation.allows("selectMovie"))
                                .accessibilityIdentifier("library.movie." + entry.id)
                                .accessibilityAddTraits(entry.id == presentation.selectedID ? .isSelected : [])
                            }
                        }
                    }
                }
            }
            .padding(SyncWatchTokens.layoutPanelPadding)
        }
    }

    private var details: some View {
        SyncWatchPanel(theme: theme) {
            if let entry = presentation.selected {
                ScrollView {
                    VStack(alignment: .leading, spacing: SyncWatchTokens.layoutPanelGap) {
                        Text(text("selectedMovie")).foregroundStyle(theme.textSecondary)
                        Text(entry.title).font(.system(size: SyncWatchTokens.typeTitleSize, weight: .heavy)).lineLimit(
                            2
                        )
                        .minimumScaleFactor(0.65).textSelection(.enabled)
                        ViewThatFits(in: .horizontal) {
                            HStack {
                                metric("duration")
                                metric("resolution")
                                metric("audio")
                                metric("subtitles")
                            }.frame(minWidth: 500)
                            VStack(spacing: SyncWatchTokens.controlCompactGap) {
                                HStack {
                                    metric("duration")
                                    metric("resolution")
                                }
                                HStack {
                                    metric("audio")
                                    metric("subtitles")
                                }
                            }
                        }
                        if presentation.state == .missingMedia {
                            Text(text("missingMedia")).foregroundStyle(theme.accentSoft)
                        }
                        ViewThatFits(in: .horizontal) {
                            HStack {
                                watchActions
                            }.fixedSize(horizontal: true, vertical: false)
                            VStack(alignment: .leading) { watchActions }
                        }
                        VStack(alignment: .leading, spacing: SyncWatchTokens.controlCompactGap) {
                            Text(text("fileLocation"))
                            Text(entry.location).foregroundStyle(theme.textSecondary).lineLimit(2).textSelection(
                                .enabled)
                        }
                        .padding(SyncWatchTokens.layoutPanelPadding).frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            theme.backgroundDeep,
                            in: RoundedRectangle(cornerRadius: SyncWatchTokens.controlButtonRadius))
                    }
                    .padding(SyncWatchTokens.layoutDetailPadding)
                }
            } else {
                Text(text("selectMovie")).foregroundStyle(theme.textSecondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }

    @ViewBuilder private var watchActions: some View {
        action("startWatching", title: "startWatching", filled: true)
        action("continueWatching", title: "continueWatching")
        action("endWatching", title: "endWatching")
    }

    private func metric(_ title: String) -> some View {
        VStack(alignment: .leading, spacing: SyncWatchTokens.controlCompactGap) {
            Text(text(title)).foregroundStyle(theme.textSecondary)
            Text(text("unknown")).fontWeight(.semibold)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private func information(_ title: String, message: String) -> some View {
        SyncWatchPanel(theme: theme) {
            VStack(alignment: .leading, spacing: SyncWatchTokens.layoutPanelGap) {
                Text(text(title)).font(.system(size: SyncWatchTokens.typeSectionSize, weight: .bold))
                Text(text(message)).foregroundStyle(theme.textSecondary)
                Spacer(minLength: 0)
                if title == "roomStatus" { action("openCall", title: "openCall") }
            }.padding(SyncWatchTokens.layoutPanelPadding)
        }
    }

    private func action(_ id: String, title: String, filled: Bool = false) -> some View {
        Button(text(title)) { emit(id) }
            .buttonStyle(SyncWatchButtonStyle(theme: theme, filled: filled))
            .disabled(!presentation.allows(id))
            .accessibilityIdentifier("library." + id)
    }
}

public struct DesignGallery: View {
    @State private var state = LibraryVisualState.selected
    @State private var language = "en"
    @State private var dark = true
    @State private var selectedID: String?
    @State private var lastAction = ""

    public init() {}

    public var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(SyncWatchCopy.text("gallery", language: language))
                Picker("State", selection: $state) {
                    ForEach(LibraryVisualState.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                }
                Picker("Language", selection: $language) {
                    Text("English").tag("en")
                    Text("Русский").tag("ru")
                }
                Toggle("Dark", isOn: $dark)
                Text(lastAction).lineLimit(1)
            }.padding(SyncWatchTokens.layoutPanelPadding)
            LibraryWorkspace(presentation: presentation, language: language) { action, value in
                lastAction = action
                if action == "selectMovie" { selectedID = value }
            }
        }
        .preferredColorScheme(dark ? .dark : .light)
    }

    private var presentation: LibraryPresentation {
        var value = LibraryPresentation.gallery(state)
        if let selectedID { value.selectedID = selectedID }
        return value
    }
}

// First-party geometric mark, identical normalized points in all three renderers.
private struct PlayMark: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.width * 0.25, y: rect.height * 0.15))
        path.addLine(to: CGPoint(x: rect.width * 0.85, y: rect.height * 0.5))
        path.addLine(to: CGPoint(x: rect.width * 0.25, y: rect.height * 0.85))
        path.closeSubpath()
        return path
    }
}
