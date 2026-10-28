import AppKit
import SwiftUI
import SyncWatchBridge
import SyncWatchDesign
import SyncWatchDomain
import SyncWatchPlayback

/// Explicit local development entry; room/watch capabilities remain with their coordinator.
struct LocalPlaybackLaunch {
    let file: URL
    let package: URL
    let report: URL?
    static func read(_ arguments: [String] = CommandLine.arguments) -> Self? {
        guard let index = arguments.firstIndex(of: "--local-playback"), index + 1 < arguments.count else { return nil }
        let package = MediaConfiguration.read(arguments).package
        let report = arguments.firstIndex(of: "--playback-report").flatMap { i in
            i + 1 < arguments.count ? URL(filePath: arguments[i + 1]) : nil
        }
        return Self(file: URL(filePath: arguments[index + 1]), package: package, report: report)
    }
}

@MainActor final class PlaybackController: ObservableObject {
    @Published private(set) var presentation = PlayerPresentation()
    @Published private(set) var failed = false
    @Published private(set) var sharedState: HelperSessionState?
    private var sharedSession: HelperSession?
    private var requiresSharedAdmission: Bool
    private var sharedMediaPreparation = SharedMediaPreparation()
    private var sharedAuthority: (@MainActor () -> Bool)?
    let player = VLCPlayback()
    private(set) var scope: PlaybackScope
    private(set) lazy var tracks = LocalPlaybackTracks(player: player, scope: { [weak self] in self?.scope })
    private let launch: LocalPlaybackLaunch
    private let runtime: VLCPlaybackRuntime?
    private var polling: Task<Void, Never>?
    private(set) var view: NSView?
    private(set) var window: NSWindow?
    private var closing = false
    private var closed = false
    private let allocateScope: Bool
    private let initialPositionMs: Int64
    private var selection: LibraryMediaSelection?
    private let onLoaded: @MainActor (PlaybackScope) -> Void
    private let onObservation: @MainActor (PlaybackObservation) -> Void
    private let onNavigation: (@MainActor (String) -> Void)?
    private let onFailure: (@MainActor () -> Void)?

    init(
        launch: LocalPlaybackLaunch, runtime: VLCPlaybackRuntime? = nil, scope: PlaybackScope? = nil,
        positionMs: Int64 = 0,
        selection: LibraryMediaSelection? = nil,
        requiresSharedAdmission: Bool = false,
        onLoaded: @escaping @MainActor (PlaybackScope) -> Void = { _ in },
        onObservation: @escaping @MainActor (PlaybackObservation) -> Void = { _ in },
        onNavigation: (@MainActor (String) -> Void)? = nil, onFailure: (@MainActor () -> Void)? = nil
    ) {
        self.launch = launch
        self.runtime = runtime
        self.scope = scope ?? .fresh()
        allocateScope = scope == nil
        initialPositionMs = positionMs
        self.selection = selection
        self.requiresSharedAdmission = requiresSharedAdmission
        self.onLoaded = onLoaded
        self.onObservation = onObservation
        self.onNavigation = onNavigation
        self.onFailure = onFailure
        presentation.title = launch.file.lastPathComponent
        presentation.enabledActions = navigationActions
    }
    private var navigationActions: Set<String> {
        onNavigation == nil ? ["endWatching", "toggleFullscreen"] : ["endWatching", "toggleFullscreen", "showLibrary"]
    }
    func prepareSharedMedia() async throws -> MediaDescriptor {
        guard !closing, let selection else { throw HelperSessionFailure.unavailable }
        let descriptor = try await sharedMediaPreparation.prepare(selection, player: player, scope: scope)
        guard !closing else { throw CancellationError() }
        return descriptor
    }
    func requireSharedAdmission() {
        requiresSharedAdmission = true
        gateSharedActions()
    }
    func admitSharedPlayback() throws {
        guard sharedSession != nil, sharedState?.connection == .connected, sharedState?.ready == true,
            sharedAuthority?() != false
        else { throw HelperSessionFailure.unavailable }
        // Syncplay can clear its readiness flag when this user pauses. That does
        // not revoke the initial admission or prevent the next Play intent.
        requiresSharedAdmission = false
    }
    func revokeShared(releaseAdmission: Bool = false) async {
        requireSharedAdmission()
        sharedAuthority = nil
        let session = sharedSession
        sharedSession = nil
        sharedState = nil
        let preparation = sharedMediaPreparation
        await preparation.close()
        await session?.close()
        try? await player.setPaused(true, scope: scope)
        guard !closing else { return }
        sharedMediaPreparation = SharedMediaPreparation()
        requiresSharedAdmission = !releaseAdmission
    }
    /// The room coordinator must admit the selected media before transferring
    /// this transport. Native playback ownership stays with this controller.
    func connectShared(
        transport: any HelperTransport, endpoint: SyncplayEndpoint, media: SharedMedia, revision: String,
        requireDeclaredIdentity: Bool = false, authority: (@MainActor () -> Bool)? = nil
    )
        async throws
    {
        do {
            guard !closing, view != nil, sharedSession == nil else { throw HelperSessionFailure.unavailable }
            try await sharedMediaPreparation.validate(player: player, scope: scope)
            guard !closing, sharedSession == nil, authority?() ?? true else { throw HelperSessionFailure.unavailable }
            sharedAuthority = authority
            let session = try HelperSession(
                transport: transport, player: player, nativeScope: scope,
                endpoint: endpoint, media: media, revision: revision,
                requireDeclaredIdentity: requiresSharedAdmission || requireDeclaredIdentity
            ) { [weak self] state in
                self?.sharedState = state
                self?.gateSharedActions()
            }
            sharedSession = session
            sharedState = session.state
            gateSharedActions()
            try session.start()
        } catch {
            await transport.close()
            throw error
        }
    }
    private func gateSharedActions() {
        if (requiresSharedAdmission || sharedSession != nil)
            && (sharedAuthority?() == false || sharedState?.connection != .connected
                || (requiresSharedAdmission && sharedState?.ready != true))
        {
            presentation.enabledActions.subtract(["playPause", "seek", "skip"])
        }
    }
    func attach(_ view: NSView) {
        guard self.view == nil, !closing else { return }
        self.view = view
        window = view.window
        polling = Task { [self] in
            do {
                if allocateScope { scope = try scope.replacingMedia() }
                let address = UInt(bitPattern: Unmanaged.passUnretained(view).toOpaque())
                if let runtime {
                    try await player.open(runtime: runtime, appKitSurfaceAddress: address)
                } else {
                    try await player.open(package: launch.package, appKitSurfaceAddress: address)
                }
                try Task.checkCancellation()
                try await player.load(launch.file, scope: scope)
                onLoaded(scope)
                var resumePending = initialPositionMs > 0
                if let report = launch.report {
                    Task { await PlaybackAcceptance.run(controller: self, report: report) }
                }
                while !Task.isCancelled {
                    let observation = try await player.observe(scope)
                    guard !closing else { break }
                    if observation.status == .failed { throw PlaybackFailure.engine }
                    if resumePending, observation.status == .ready {
                        resumePending = false
                        if observation.seekable {
                            // A saved position seeds a request; only the next native observation is published.
                            try? await player.seek(
                                to: min(initialPositionMs, observation.durationMs ?? initialPositionMs), scope: scope)
                            continue
                        }
                    }
                    apply(observation)
                    onObservation(observation)
                    try await Task.sleep(for: .milliseconds(100))
                }
            } catch is CancellationError {
            } catch {
                if !closing {
                    if let report = launch.report {
                        await PlaybackAcceptance.fail(controller: self, report: report, error: error)
                        return
                    }
                    failed = true
                    tracks.dismiss()
                    presentation.enabledActions = ["endWatching"]
                    onFailure?()
                }
            }
        }
    }
    private func apply(_ value: PlaybackObservation) {
        presentation.state =
            value.ended
            ? .ended
            : value.buffering ? .buffering : value.status != .ready ? .loading : value.paused ? .paused : .playing
        presentation.positionMs = value.positionMs
        presentation.durationMs = value.durationMs ?? 0
        presentation.volume = value.volume ?? presentation.volume
        presentation.muted = value.muted
        presentation.enabledActions = navigationActions.union(["playPause"])
        if value.volume != nil { presentation.enabledActions.formUnion(["setMovieVolume", "muteMovie"]) }
        if value.seekable { presentation.enabledActions.formUnion(["seek", "skip"]) }
        if value.status == .ready, !value.ended {
            presentation.enabledActions.formUnion(["selectAudio", "selectSubtitles"])
        } else {
            tracks.dismiss()
        }
        gateSharedActions()
    }
    func action(_ action: String, value: Double?) {
        guard !closing else { return }
        gateSharedActions()
        guard presentation.enabledActions.contains(action) else { return }
        if action == "selectAudio" || action == "selectSubtitles" {
            tracks.open(action == "selectAudio" ? "audio" : "subtitles")
            return
        }
        if action == "showLibrary" || action == "endWatching" || action == "toggleFullscreen" { tracks.dismiss() }
        if action == "endWatching" || action == "showLibrary", let onNavigation {
            onNavigation(action)
            return
        }
        if action == "endWatching" {
            let ownedWindow = window
            Task {
                await close()
                ownedWindow?.close()
            }
            return
        }
        if action == "toggleFullscreen" {
            if #unavailable(macOS 15) {
                window?.collectionBehavior.remove(.fullScreenNone)
                window?.collectionBehavior.insert(.fullScreenPrimary)
            }
            window?.toggleFullScreen(nil)
            return
        }
        if let sharedSession, action == "playPause" || action == "seek" {
            do {
                if action == "playPause" {
                    try sharedSession.togglePause()
                } else if let value, value.isFinite, value >= 0, value <= Double(WatchSession.maximumPositionMs) {
                    try sharedSession.seek(Int64(value))
                }
            } catch {
                // A rejected shared intent leaves the observation authoritative.
            }
            return
        }
        let paused = presentation.playing
        let volume = presentation.volume
        let muted = presentation.muted
        Task {
            do {
                switch action {
                case "playPause": try await player.setPaused(paused, scope: scope)
                case "seek":
                    if let value, value.isFinite, value >= 0, value <= Double(WatchSession.maximumPositionMs) {
                        try await player.seek(to: Int64(value), scope: scope)
                    }
                case "setMovieVolume": if let value { try await player.setVolume(value, muted: muted, scope: scope) }
                case "muteMovie": try await player.setVolume(volume, muted: !muted, scope: scope)
                default: break
                }
            } catch {
                // A rejected request does not acknowledge a different state.
            }
        }
    }
    func detach(_ surface: NSView) {
        let ownedWindow = surface.window ?? window
        Task {
            await close()
            withExtendedLifetime((surface, ownedWindow)) {}
        }
    }
    func close() async {
        guard !closed else { return }
        closing = true
        presentation.enabledActions = []
        polling?.cancel()
        await tracks.close()
        await sharedMediaPreparation.close()
        await sharedSession?.close()
        sharedSession = nil
        await player.close()
        await polling?.value
        polling = nil
        view = nil
        window = nil
        withExtendedLifetime(selection) {}
        selection = nil
        closed = true
    }
}

struct PlaybackPane: View {
    @ObservedObject var controller: PlaybackController
    var language: String
    var body: some View {
        PlaybackTrackPane(controller: controller, tracks: controller.tracks, language: language)
    }
}

private struct PlaybackTrackPane: View {
    @ObservedObject var controller: PlaybackController
    @ObservedObject var tracks: LocalPlaybackTracks
    var language: String
    var body: some View {
        PlayerChrome(
            presentation: controller.presentation, language: language,
            videoSurface: AnyView(VideoSurface(onAttach: controller.attach, onDetach: controller.detach)),
            selectionMenu: tracks.menu, onAction: controller.action
        ).selectionHandlers(onSelection: tracks.select, onDismiss: tracks.dismiss)
    }
}

struct PlaybackWorkspace: View {
    @StateObject private var controller: PlaybackController
    @StateObject private var preferences = AppearancePreferences(
        store: FileLocalStateStore(url: AppearancePreferences.defaultURL))
    init(launch: LocalPlaybackLaunch) { _controller = StateObject(wrappedValue: PlaybackController(launch: launch)) }
    @ViewBuilder var body: some View {
        if #available(macOS 15, *) {
            content.windowFullScreenBehavior(.enabled)
        } else {
            content
        }
    }
    private var content: some View {
        PlaybackPane(controller: controller, language: preferences.state.preferences.language)
            .preferredColorScheme(preferences.colorScheme)
            .environment(\.locale, Locale(identifier: preferences.state.preferences.language))
            .alert(
                SyncWatchCopy.text("playbackFailed", language: preferences.state.preferences.language),
                isPresented: Binding(
                    get: { controller.failed }, set: { _ in }
                )
            ) {
                Button(SyncWatchCopy.text("endWatching", language: preferences.state.preferences.language)) {
                    controller.action("endWatching", value: nil)
                }
            }
    }
}
