import SwiftUI

public enum PlayerVisualState: String, CaseIterable, Sendable {
    case loading, paused, playing, buffering, fullscreen, connectionInterrupted, ended
}

/// Observations and capabilities only. User input emits requests without assuming engine acknowledgement.
public struct PlayerPresentation: Sendable {
    public var state: PlayerVisualState = .loading
    public var title = ""
    public var positionMs: Int64 = 0
    public var durationMs: Int64 = 0
    public var volume = 1.0
    public var muted = false
    public var skipSeconds = 10
    public var hasPrevious = false
    public var hasNext = false
    public var enabledActions: Set<String> = []

    public init() {}
    public var isValid: Bool {
        (0...SyncWatchPlayer.maximumPositionMs).contains(durationMs)
            && (0...max(0, durationMs)).contains(positionMs)
            && volume.isFinite && (0...1).contains(volume) && (1...600).contains(skipSeconds)
    }
    public var playing: Bool { state == .playing || state == .fullscreen }
    public var displayedPosition: Double { min(Double(max(0, positionMs)), displayedDuration) }
    public var displayedDuration: Double { Double(min(max(0, durationMs), SyncWatchPlayer.maximumPositionMs)) }
    public func allows(_ action: String) -> Bool {
        guard enabledActions.contains(action), SyncWatchPlayer.actions.contains(action) else { return false }
        switch action {
        case "playPause", "seek", "skip", "previousFile", "nextFile":
            guard isValid, [.paused, .playing, .fullscreen].contains(state) else { return false }
            if action == "seek" || action == "skip" { return durationMs > 0 }
            if action == "previousFile" { return hasPrevious }
            if action == "nextFile" { return hasNext }
            return true
        case "setMovieVolume", "muteMovie": return isValid
        default: return true
        }
    }
    public func dispatch(_ action: String, value: Double? = nil, to handler: (String, Double?) -> Void) {
        guard allows(action) else { return }
        switch action {
        case "seek":
            guard let value, value.isFinite, value.rounded() == value, (0...Double(durationMs)).contains(value) else {
                return
            }
        case "skip":
            guard let value, value == -1 || value == 1, allows("seek") else { return }
            let target = min(Double(durationMs), max(0, Double(positionMs) + value * Double(skipSeconds) * 1000))
            if target != Double(positionMs) { handler("seek", target) }
            return
        case "setMovieVolume":
            guard let value, value.isFinite, (0...1).contains(value) else { return }
        default: guard value == nil else { return }
        }
        handler(action, value)
    }
    public static func time(_ milliseconds: Double) -> String {
        let seconds =
            Int(min(Double(SyncWatchPlayer.maximumPositionMs), max(0, milliseconds.isFinite ? milliseconds : 0))) / 1000
        return seconds >= 3600
            ? String(format: "%d:%02d:%02d", seconds / 3600, (seconds / 60) % 60, seconds % 60)
            : String(format: "%02d:%02d", seconds / 60, seconds % 60)
    }
    public static func gallery(_ state: PlayerVisualState) -> Self {
        var p = Self()
        p.state = state
        p.title = SyncWatchCopy.galleryMovies[1]
        p.durationMs = state == .loading ? 0 : 5_400_000
        p.positionMs = state == .ended ? p.durationMs : min(754_000, p.durationMs)
        p.volume = 0.7
        p.hasPrevious = true
        p.hasNext = true
        p.enabledActions = Set(SyncWatchPlayer.actions)
        return p
    }
}

public struct PlayerIcon: Shape {
    public var name: String
    public init(_ name: String) { self.name = name }
    public func path(in rect: CGRect) -> Path {
        var path = Path()
        for polygon in SyncWatchPlayer.icons[name] ?? [] {
            for index in stride(from: 0, to: polygon.count, by: 2) {
                let point = CGPoint(
                    x: rect.minX + polygon[index] / 20 * rect.width,
                    y: rect.minY + polygon[index + 1] / 20 * rect.height)
                if index == 0 { path.move(to: point) } else { path.addLine(to: point) }
            }
            path.closeSubpath()
        }
        return path
    }
}

private struct PlayerButtonStyle: ButtonStyle {
    var theme: SyncWatchTheme
    var prominent: Bool
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(prominent ? SyncWatchTokens.colorDarkText : theme.text)
            .frame(
                width: prominent ? SyncWatchTokens.controlPlayerProminentSize : SyncWatchTokens.controlPlayerButtonSize,
                height: prominent ? SyncWatchTokens.controlPlayerProminentSize : SyncWatchTokens.controlPlayerButtonSize
            )
            .background(prominent ? theme.accent : theme.surfaceRaised, in: Circle())
            .overlay(Circle().stroke(theme.border, lineWidth: SyncWatchTokens.controlBorderWidth))
            .opacity(enabled ? (configuration.isPressed ? 0.75 : 1) : 0.4)
            .contentShape(Circle())
    }
}

struct PlayerRange: View {
    var value: Double
    var maximum: Double
    var label: String
    var enabled: Bool
    var step: Double
    var accessibilityText: String
    var theme: SyncWatchTheme
    var onChange: (Double) -> Void
    @FocusState private var focused: Bool

    private func adjust(_ delta: Double) {
        if enabled { onChange(min(maximum, max(0, value + delta))) }
    }
    var body: some View {
        GeometryReader { geometry in
            let radius = SyncWatchTokens.controlPlayerSliderThumbSize / 2
            let span = max(1, geometry.size.width - radius * 2)
            let fraction = value / max(1, maximum)
            ZStack(alignment: .leading) {
                Capsule().fill(theme.border).frame(height: SyncWatchTokens.controlSliderTrackHeight)
                    .padding(.horizontal, radius)
                Capsule().fill(theme.accent).frame(
                    width: span * fraction, height: SyncWatchTokens.controlSliderTrackHeight
                )
                .offset(x: radius)
                Circle().fill(theme.accent)
                    .frame(
                        width: SyncWatchTokens.controlPlayerSliderThumbSize,
                        height: SyncWatchTokens.controlPlayerSliderThumbSize
                    )
                    .offset(x: span * fraction)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0).onChanged { drag in
                    guard enabled else { return }
                    focused = true
                    onChange(min(maximum, max(0, Double((drag.location.x - radius) / span) * maximum)))
                })
        }
        .frame(height: SyncWatchTokens.controlPlayerSliderHeight)
        .opacity(enabled ? 1 : 0.4)
        .focusable(enabled).focused($focused)
        .overlay(
            RoundedRectangle(cornerRadius: SyncWatchTokens.controlFieldRadius)
                .stroke(focused ? theme.accentSoft : .clear, lineWidth: SyncWatchTokens.controlBorderWidth)
        )
        .onMoveCommand { direction in
            switch direction {
            case .left, .down: adjust(-step)
            case .right, .up: adjust(step)
            default: break
            }
        }
        .accessibilityElement(children: .ignore).accessibilityLabel(label)
        .accessibilityValue(accessibilityText)
        .accessibilityAdjustableAction { direction in
            switch direction {
            case .increment: adjust(step)
            case .decrement: adjust(-step)
            @unknown default: break
            }
        }
        .disabled(!enabled)
    }
}

public struct PlayerChrome: View {
    public var presentation: PlayerPresentation
    public var language: String
    public var videoSurface: AnyView?
    public var onAction: (String, Double?) -> Void
    @Environment(\.colorScheme) private var scheme
    private var theme: SyncWatchTheme { .resolve(scheme) }
    private func t(_ key: String) -> String { SyncWatchCopy.text(key, language: language) }
    private func emit(_ action: String, _ value: Double? = nil) {
        presentation.dispatch(action, value: value, to: onAction)
    }

    public init(
        presentation: PlayerPresentation = PlayerPresentation(), language: String = "en", videoSurface: AnyView? = nil,
        onAction: @escaping (String, Double?) -> Void = { _, _ in }
    ) {
        self.presentation = presentation
        self.language = language
        self.videoSurface = videoSurface
        self.onAction = onAction
    }

    private func button(
        _ action: String, icon: String, label: String? = nil, value: Double? = nil, prominent: Bool = false
    ) -> some View {
        Button {
            emit(action, value)
        } label: {
            PlayerIcon(icon).frame(
                width: SyncWatchTokens.controlPlayerIconSize, height: SyncWatchTokens.controlPlayerIconSize)
        }
        .buttonStyle(PlayerButtonStyle(theme: theme, prominent: prominent))
        .disabled(!presentation.allows(action))
        .help(t(label ?? action)).accessibilityLabel(t(label ?? action)).accessibilityIdentifier(
            "player." + (label ?? action))
    }

    public var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: SyncWatchTokens.controlCompactGap) {
                button("showLibrary", icon: "library")
                Text(presentation.title).lineLimit(1).truncationMode(.middle).frame(
                    maxWidth: .infinity, alignment: .leading)
                Text(t(presentation.state.rawValue)).foregroundStyle(theme.textSecondary).lineLimit(1)
                button("openCall", icon: "call")
                button("toggleFullscreen", icon: "fullscreen")
                button("endWatching", icon: "end")
            }
            .padding(.horizontal, SyncWatchTokens.layoutPanelPadding)
            .frame(height: SyncWatchTokens.layoutPlayerToolbarHeight)
            .background(theme.backgroundDeep)
            ZStack {
                SyncWatchTokens.colorSharedVideoSurface
                videoSurface
            }.frame(maxWidth: .infinity, maxHeight: .infinity).clipped().accessibilityLabel(t("videoSurface"))
            VStack(spacing: 0) {
                HStack(spacing: SyncWatchTokens.controlCompactGap) {
                    Text(PlayerPresentation.time(presentation.displayedPosition)).frame(
                        width: SyncWatchTokens.layoutPlayerTimeWidth)
                    PlayerRange(
                        value: presentation.displayedPosition, maximum: presentation.displayedDuration,
                        label: t("seek"), enabled: presentation.allows("seek"), step: 1000,
                        accessibilityText: PlayerPresentation.time(presentation.displayedPosition), theme: theme
                    ) {
                        emit("seek", $0.rounded())
                    }.accessibilityIdentifier("player.seek")
                    Text(PlayerPresentation.time(presentation.displayedDuration)).frame(
                        width: SyncWatchTokens.layoutPlayerTimeWidth)
                }.frame(height: SyncWatchTokens.controlPlayerSliderHeight)
                HStack(spacing: 0) {
                    HStack(spacing: SyncWatchTokens.controlCompactGap) {
                        button("openPlayerSettings", icon: "settings", label: "playerSettings")
                        button("openPlaylist", icon: "playlist", label: "playlist")
                    }.frame(maxWidth: .infinity, alignment: .leading)
                    HStack(spacing: SyncWatchTokens.controlCompactGap) {
                        button("previousFile", icon: "previous")
                        button("skip", icon: "backward", label: "skipBackward", value: -1)
                        button(
                            "playPause", icon: presentation.playing ? "pause" : "play",
                            label: presentation.playing ? "pause" : "play", prominent: true)
                        button("skip", icon: "forward", label: "skipForward", value: 1)
                        button("nextFile", icon: "next")
                    }
                    HStack(spacing: SyncWatchTokens.controlCompactGap) {
                        button("selectSubtitles", icon: "subtitles", label: "subtitles")
                        button("selectAudio", icon: "audio", label: "audioTracks")
                        button(
                            "muteMovie", icon: presentation.muted ? "muted" : "volume",
                            label: presentation.muted ? "unmuteMovie" : "muteMovie")
                        PlayerRange(
                            value: presentation.isValid ? presentation.volume : 0, maximum: 1,
                            label: t("setMovieVolume"), enabled: presentation.allows("setMovieVolume"), step: 0.05,
                            accessibilityText: String(
                                format: "%.0f%%", (presentation.isValid ? presentation.volume : 0) * 100), theme: theme
                        ) {
                            emit("setMovieVolume", $0)
                        }.frame(width: SyncWatchTokens.layoutPlayerVolumeWidth)
                            .accessibilityIdentifier("player.setMovieVolume")
                    }.frame(maxWidth: .infinity, alignment: .trailing)
                }.frame(maxHeight: .infinity)
            }
            .padding(.horizontal, SyncWatchTokens.layoutPanelPadding)
            .frame(height: SyncWatchTokens.layoutPlayerFooterHeight).background(theme.backgroundDeep)
        }
        .font(.system(size: SyncWatchTokens.typePlayerLabelSize)).foregroundStyle(theme.text)
        .frame(minWidth: SyncWatchTokens.layoutMinimumWidth, minHeight: SyncWatchTokens.layoutMinimumHeight)
    }
}

public struct PlayerGallery: View {
    @State private var presentation = PlayerPresentation.gallery(.paused)
    @State private var language = "en"
    @State private var dark = true
    @State private var lastAction = ""
    @State private var showPlayerSettings = false
    @State private var savedPlayerSettings = SyncWatchPlayerSettings.defaults
    @State private var playerSettingsEditor = PlayerSettingsEditor()
    @State private var dialogOffset = CGSize.zero
    public init() {}
    public var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(SyncWatchCopy.text("playerFixture", language: language))
                Picker("State", selection: Binding(get: { presentation.state }, set: { presentation = .gallery($0) })) {
                    ForEach(PlayerVisualState.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                }.frame(width: 240)
                Picker("Language", selection: $language) {
                    Text("English").tag("en")
                    Text("Русский").tag("ru")
                }.frame(width: 150)
                Toggle("Dark", isOn: $dark)
                Text(lastAction).lineLimit(1)
            }.padding(SyncWatchTokens.controlCompactGap)
            PlayerChrome(
                presentation: presentation, language: language,
                videoSurface: AnyView(
                    Text(SyncWatchCopy.text("playerFixture", language: language)).foregroundStyle(
                        SyncWatchTokens.colorDarkText)
                )
            ) { action, value in
                lastAction = action + (value.map { ": \($0)" } ?? "")
                switch action {
                case "seek": presentation.positionMs = Int64(value ?? 0)
                case "playPause": presentation.state = presentation.playing ? .paused : .playing
                case "setMovieVolume": presentation.volume = value ?? 0
                case "muteMovie": presentation.muted.toggle()
                case "openPlayerSettings":
                    playerSettingsEditor = PlayerSettingsEditor(
                        values: savedPlayerSettings, editableFields: Set(SyncWatchPlayerSettings.defaults.keys),
                        canSave: true)
                    dialogOffset = .zero
                    showPlayerSettings = true
                default: break
                }
            }
        }
        .disabled(showPlayerSettings)
        .overlay {
            if showPlayerSettings {
                GeometryReader { geometry in
                    ZStack {
                        SyncWatchTheme.resolve(dark ? .dark : .light).backgroundDeep.opacity(0.6).contentShape(
                            Rectangle()
                        ).onTapGesture {}
                        PlayerSettingsDialog(
                            editor: $playerSettingsEditor, language: language,
                            onSave: { values in
                                savedPlayerSettings = values
                                presentation.skipSeconds = Int(values["skipSeconds"] ?? "10") ?? 10
                                presentation.volume = (Double(values["defaultVolume"] ?? "100") ?? 100) / 100
                                return true
                            }, onClose: { showPlayerSettings = false },
                            onMove: { delta in
                                let maxX = max(0, (geometry.size.width - SyncWatchTokens.layoutSettingsWidth) / 2)
                                let maxY = max(
                                    0, (geometry.size.height - SyncWatchTokens.layoutPlayerSettingsHeight) / 2)
                                dialogOffset = CGSize(
                                    width: min(maxX, max(-maxX, dialogOffset.width + delta.width)),
                                    height: min(maxY, max(-maxY, dialogOffset.height + delta.height)))
                            }
                        ).offset(dialogOffset)
                    }
                }
            }
        }
        .preferredColorScheme(dark ? .dark : .light)
    }
}
