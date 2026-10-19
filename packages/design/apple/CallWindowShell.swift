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

/// Owned content and requests only. Composition is compiled from the shared Call document.
public struct CallWindowShell: View {
    public var presentation: CallPresentation
    public var language: String
    public var remoteSurface: AnyView?
    public var localPreview: AnyView?
    public var onAction: (CallRequest) -> Void
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
    public var body: some View {
        DesignSurface(
            "Call",
            context: DesignBindings.call(presentation, hasRemote: remoteSurface != nil, hasLocal: localPreview != nil),
            language: language,
            slots: ownedSlots
        ) { event in
            let values = event.value?.split(separator: ",").compactMap { Double($0) } ?? []
            presentation.dispatch(CallRequest(event.action, values), to: onAction)
        }
    }
    private var ownedSlots: [String: AnyView] {
        var slots: [String: AnyView] = [:]
        if presentation.showsRemoteSurface { slots["remoteCallSurface"] = remoteSurface }
        if presentation.showsLocalPreview { slots["localCameraPreview"] = localPreview }
        return slots
    }
}
