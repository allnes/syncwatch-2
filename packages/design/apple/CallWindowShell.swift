import SwiftUI

public enum CallVisualState: String, CaseIterable, Sendable {
    case idle, opening, webSurfaceReady, userActionRequired, failed, closed
}
public enum CallPreviewState: String, CaseIterable, Sendable {
    case cameraStarting, cameraActive, cameraDisabled, permissionDenied, deviceUnavailable
}
public struct CallRequest: Equatable, Sendable {
    public let action: String
    public let values: [Double]
    public init(_ action: String, _ values: [Double] = []) {
        self.action = action
        self.values = values
    }
}

/// Presentation observations only; readiness is not proof of joining a call.
public struct CallPresentation: Sendable {
    public var state: CallVisualState = .idle
    public var preview: CallPreviewState = .cameraDisabled
    public var joined: Bool?
    public var microphoneEnabled: Bool?
    public var cameraEnabled: Bool?
    public var volume: Double?
    public var pinned = false
    public var fullscreen = false
    public var minimized = false
    public var enabledActions: Set<String> = []
    public init() {}
    public var showsRemoteSurface: Bool { state == .webSurfaceReady || state == .userActionRequired }
    public var showsLocalPreview: Bool {
        state == .webSurfaceReady && joined == true && cameraEnabled == true && preview == .cameraActive
    }
    public var displayedVolume: Double { volume.flatMap { $0.isFinite ? min(1, max(0, $0)) : nil } ?? 0 }
    public func previewLabel(hasSurface: Bool) -> String {
        if preview != .cameraActive { return preview.rawValue }
        if cameraEnabled == false { return CallPreviewState.cameraDisabled.rawValue }
        return showsLocalPreview && hasSurface ? "cameraActive" : "cameraStarting"
    }
    public func allows(_ action: String) -> Bool {
        guard enabledActions.contains(action), SyncWatchCall.actions.contains(action) else { return false }
        switch action {
        case "setCallVolume", "setMicrophoneEnabled", "setCameraEnabled", "hangUp":
            guard state == .webSurfaceReady, joined == true else { return false }
            if action == "setCallVolume" { return volume.map { $0.isFinite && (0...1).contains($0) } ?? false }
            if action == "setMicrophoneEnabled" { return microphoneEnabled != nil }
            if action == "setCameraEnabled" { return cameraEnabled != nil }
            return true
        default: return true
        }
    }
    public func dispatch(_ request: CallRequest, to handler: (CallRequest) -> Void) {
        guard allows(request.action), request.values.allSatisfy(\.isFinite) else { return }
        let v = request.values
        switch SyncWatchCall.actionKinds[request.action] {
        case "none": guard v.isEmpty else { return }
        case "boolean": guard v.count == 1, v[0] == 0 || v[0] == 1 else { return }
        case "volume": guard v.count == 1, (0...1).contains(v[0]) else { return }
        case "delta": guard v.count == 2, v.allSatisfy({ abs($0) <= SyncWatchCall.maximumExtent }) else { return }
        case "size":
            guard v.count == 2, (SyncWatchTokens.layoutCallMinimumWidth...SyncWatchCall.maximumExtent).contains(v[0]),
                (SyncWatchTokens.layoutCallMinimumHeight...SyncWatchCall.maximumExtent).contains(v[1])
            else { return }
        default: return
        }
        handler(request)
    }
    public static func gallery(_ item: CallGalleryCase) -> Self {
        var p = Self()
        p.state = CallVisualState(rawValue: item.state) ?? .idle
        p.preview = CallPreviewState(rawValue: item.preview) ?? .cameraDisabled
        p.joined = p.state == .webSurfaceReady
        p.microphoneEnabled = true
        p.cameraEnabled = p.preview != .cameraDisabled
        p.volume = 0.7
        p.enabledActions = Set(SyncWatchCall.actions)
        return p
    }
    public func applyingFixture(_ request: CallRequest) -> Self {
        var p = self
        switch request.action {
        case "pin": p.pinned.toggle()
        case "fullscreen": p.fullscreen.toggle()
        case "minimize": p.minimized = true
        case "restore": p.minimized = false
        case "setCallVolume": p.volume = request.values.first
        case "setMicrophoneEnabled": p.microphoneEnabled = request.values.first == 1
        case "setCameraEnabled":
            p.cameraEnabled = request.values.first == 1
            p.preview = p.cameraEnabled == true ? .cameraActive : .cameraDisabled
        case "close", "hangUp":
            p.state = .closed
            p.joined = false
            p.preview = .cameraDisabled
        default: break
        }
        return p
    }
}

public struct CallIcon: Shape {
    public var name: String
    public init(_ name: String) { self.name = name }
    public func path(in rect: CGRect) -> Path {
        var path = Path()
        for polygon in SyncWatchCall.icons[name] ?? [] {
            for i in stride(from: 0, to: polygon.count, by: 2) {
                let point = CGPoint(
                    x: rect.minX + polygon[i] / 20 * rect.width, y: rect.minY + polygon[i + 1] / 20 * rect.height)
                if i == 0 { path.move(to: point) } else { path.addLine(to: point) }
            }
            path.closeSubpath()
        }
        return path
    }
}
private struct CallButtonStyle: ButtonStyle {
    var theme: SyncWatchTheme
    var size: Double
    var active = false
    var destructive = false
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.frame(width: size, height: size)
            .foregroundStyle(destructive || active ? SyncWatchTokens.colorDarkText : theme.text)
            .background(
                destructive ? SyncWatchTokens.colorSharedCallHangup : active ? theme.accent : theme.surfaceRaised,
                in: Circle()
            )
            .overlay(Circle().stroke(theme.border, lineWidth: SyncWatchTokens.controlBorderWidth))
            .opacity(enabled ? (configuration.isPressed ? 0.75 : 1) : 0.4).contentShape(Circle())
    }
}

/// Owned view slots; requests never start a provider, capture devices or acknowledge teardown.
public struct CallWindowShell: View {
    public var presentation: CallPresentation
    public var language: String
    public var remoteSurface: AnyView?
    public var localPreview: AnyView?
    public var onAction: (CallRequest) -> Void
    @Environment(\.colorScheme) private var scheme
    private var theme: SyncWatchTheme { .resolve(scheme) }
    private func t(_ key: String) -> String { SyncWatchCopy.text(key, language: language) }
    private func emit(_ action: String, _ values: [Double] = []) {
        presentation.dispatch(CallRequest(action, values), to: onAction)
    }
    public init(
        presentation: CallPresentation = CallPresentation(), language: String = "en", remoteSurface: AnyView? = nil,
        localPreview: AnyView? = nil, onAction: @escaping (CallRequest) -> Void = { _ in }
    ) {
        self.presentation = presentation
        self.language = language
        self.remoteSurface = remoteSurface
        self.localPreview = localPreview
        self.onAction = onAction
    }
    private func button(
        _ action: String, _ icon: String, _ label: String, values: [Double] = [], small: Bool = false,
        active: Bool = false, slash: Bool = false
    ) -> some View {
        Button {
            emit(action, values)
        } label: {
            ZStack {
                CallIcon(icon)
                if slash { CallIcon("slash") }
            }
            .frame(width: SyncWatchTokens.layoutCallIconSize, height: SyncWatchTokens.layoutCallIconSize)
        }
        .buttonStyle(
            CallButtonStyle(
                theme: theme,
                size: small ? SyncWatchTokens.layoutCallWindowButtonSize : SyncWatchTokens.layoutCallButtonSize,
                active: active, destructive: action == "hangUp")
        )
        .disabled(!presentation.allows(action)).help(t(label)).accessibilityLabel(t(label)).accessibilityIdentifier(
            "call." + action)
    }
    public var body: some View {
        GeometryReader { geometry in
            VStack(spacing: 0) {
                HStack(spacing: SyncWatchTokens.layoutCallGap / 2) {
                    Text(t("callWindow")).lineLimit(1).truncationMode(.tail).frame(
                        maxWidth: .infinity, alignment: .leading
                    )
                    .contentShape(Rectangle()).gesture(
                        DragGesture().onEnded { emit("move", [$0.translation.width, $0.translation.height]) }
                    )
                    .accessibilityLabel(t("moveCall"))
                    .accessibilityAction(named: Text(t("moveCall"))) { emit("move", [10, 0]) }
                    button(
                        "pin", "pin", presentation.pinned ? "unpinCall" : "pinCall", small: true,
                        active: presentation.pinned)
                    button(
                        presentation.minimized ? "restore" : "minimize",
                        presentation.minimized ? "restore" : "minimize",
                        presentation.minimized ? "restoreCall" : "minimizeCall", small: true)
                    button(
                        "fullscreen", presentation.fullscreen ? "restore" : "fullscreen",
                        presentation.fullscreen ? "exitFullscreenCall" : "fullscreenCall", small: true)
                    button("close", "close", "closeCall", small: true)
                }
                .frame(height: SyncWatchTokens.layoutCallHeaderHeight).padding(
                    .horizontal, SyncWatchTokens.layoutCallInset)
                ZStack(alignment: .topLeading) {
                    SyncWatchTokens.colorSharedVideoSurface
                    if presentation.showsRemoteSurface, let remoteSurface {
                        remoteSurface
                    } else {
                        Text(
                            t(
                                "callState" + presentation.state.rawValue.prefix(1).uppercased()
                                    + presentation.state.rawValue.dropFirst())
                        )
                        .foregroundStyle(SyncWatchTokens.colorDarkText).multilineTextAlignment(.center)
                        .padding(SyncWatchTokens.layoutCallInset).frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                    ZStack {
                        theme.surfaceRaised
                        if presentation.showsLocalPreview, let localPreview {
                            localPreview
                        } else {
                            Text(t(presentation.previewLabel(hasSurface: localPreview != nil)))
                                .font(.system(size: SyncWatchTokens.typeCaptionSize)).foregroundStyle(
                                    theme.textSecondary
                                )
                                .multilineTextAlignment(.center).padding(2)
                        }
                    }
                    .frame(
                        width: SyncWatchTokens.layoutCallPreviewWidth, height: SyncWatchTokens.layoutCallPreviewHeight
                    )
                    .clipShape(RoundedRectangle(cornerRadius: SyncWatchTokens.controlFieldRadius))
                    .overlay(RoundedRectangle(cornerRadius: SyncWatchTokens.controlFieldRadius).stroke(theme.border))
                    .padding(SyncWatchTokens.layoutCallInset).accessibilityLabel(
                        t(presentation.previewLabel(hasSurface: localPreview != nil)))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity).clipped().accessibilityLabel(t("callSurface"))
                HStack(spacing: SyncWatchTokens.layoutCallGap) {
                    button(
                        "setMicrophoneEnabled", "microphone",
                        presentation.microphoneEnabled == true ? "microphoneOff" : "microphoneOn",
                        values: [presentation.microphoneEnabled == true ? 0 : 1],
                        active: presentation.microphoneEnabled == true, slash: presentation.microphoneEnabled == false)
                    button(
                        "setCameraEnabled", "camera", presentation.cameraEnabled == true ? "cameraOff" : "cameraOn",
                        values: [presentation.cameraEnabled == true ? 0 : 1],
                        active: presentation.cameraEnabled == true, slash: presentation.cameraEnabled == false)
                    button("hangUp", "end", "hangUp")
                    CallIcon(presentation.displayedVolume > 0 ? "volume" : "muted").fill(theme.textSecondary)
                        .frame(width: SyncWatchTokens.layoutCallIconSize, height: SyncWatchTokens.layoutCallIconSize)
                        .accessibilityHidden(true)
                    PlayerRange(
                        value: presentation.displayedVolume, maximum: 1, label: t("callVolume"),
                        enabled: presentation.allows("setCallVolume"),
                        step: 0.05, accessibilityText: "\(Int(presentation.displayedVolume * 100))%", theme: theme
                    ) { emit("setCallVolume", [$0]) }
                    .frame(width: SyncWatchTokens.layoutCallVolumeWidth).accessibilityIdentifier("call.setCallVolume")
                }
                .frame(maxWidth: .infinity).frame(height: SyncWatchTokens.layoutCallFooterHeight)
            }
            .background(theme.backgroundDeep)
            .overlay(alignment: .bottomTrailing) {
                CallIcon("resize").fill(theme.textSecondary).frame(
                    width: SyncWatchTokens.layoutCallResizeSize, height: SyncWatchTokens.layoutCallResizeSize
                )
                .padding(2).contentShape(Rectangle()).gesture(
                    DragGesture().onEnded {
                        emit(
                            "resize",
                            [
                                min(
                                    SyncWatchCall.maximumExtent,
                                    max(
                                        SyncWatchTokens.layoutCallMinimumWidth,
                                        geometry.size.width + $0.translation.width)),
                                min(
                                    SyncWatchCall.maximumExtent,
                                    max(
                                        SyncWatchTokens.layoutCallMinimumHeight,
                                        geometry.size.height + $0.translation.height)),
                            ])
                    }
                ).accessibilityLabel(t("resizeCall"))
                .accessibilityAction(named: Text(t("resizeCall"))) {
                    emit("resize", [geometry.size.width + 10, geometry.size.height + 10])
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: presentation.fullscreen ? 0 : SyncWatchTokens.layoutCallRadius))
            .overlay(
                RoundedRectangle(cornerRadius: presentation.fullscreen ? 0 : SyncWatchTokens.layoutCallRadius).stroke(
                    theme.border))
        }
        .frame(minWidth: SyncWatchTokens.layoutCallMinimumWidth, minHeight: SyncWatchTokens.layoutCallMinimumHeight)
        .font(.system(size: SyncWatchTokens.typePlayerLabelSize)).foregroundStyle(theme.text)
    }
}

/// Isolated, opt-in observations. No application preferences, browser or devices are used.
public struct CallGallery: View {
    @State private var selected = "ready"
    @State private var language = "en"
    @State private var dark = true
    @State private var presentation = CallPresentation.gallery(SyncWatchCall.galleryCases[2])
    @State private var last = ""
    public init() {}
    public var body: some View {
        VStack(spacing: 16) {
            HStack {
                Picker("State", selection: $selected) {
                    ForEach(SyncWatchCall.galleryCases, id: \.id) { Text($0.id).tag($0.id) }
                }.frame(width: 180)
                Picker("Language", selection: $language) {
                    Text("English").tag("en")
                    Text("Русский").tag("ru")
                }.frame(width: 140)
                Toggle("Dark", isOn: $dark)
            }
            CallWindowShell(
                presentation: presentation, language: language,
                remoteSurface: AnyView(
                    Text(SyncWatchCopy.text("remoteFixture", language: language)).foregroundStyle(.white).frame(
                        maxWidth: .infinity, maxHeight: .infinity)),
                localPreview: AnyView(
                    Text(SyncWatchCopy.text("localFixture", language: language)).font(.caption).foregroundStyle(.white)
                        .frame(maxWidth: .infinity, maxHeight: .infinity).background(
                            dark ? SyncWatchTheme.dark.accent : SyncWatchTheme.light.accent))
            ) {
                last = $0.action
                presentation = presentation.applyingFixture($0)
            }.frame(width: SyncWatchTokens.layoutCallInitialWidth, height: SyncWatchTokens.layoutCallInitialHeight)
            Text(SyncWatchCopy.text("callFixture", language: language)).font(.caption)
            Text(last).font(.caption)
        }.padding().frame(maxWidth: .infinity, maxHeight: .infinity)
            .environment(\.colorScheme, dark ? .dark : .light)
            .onChange(of: selected) { value in
                if let item = SyncWatchCall.galleryCases.first(where: { $0.id == value }) {
                    presentation = .gallery(item)
                }
            }
    }
}
