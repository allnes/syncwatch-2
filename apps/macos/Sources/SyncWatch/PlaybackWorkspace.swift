import AppKit
import SwiftUI
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
    let player = VLCPlayback()
    private(set) var scope: PlaybackScope
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
    }
    func action(_ action: String, value: Double?) {
        guard !closing else { return }
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
        PlayerChrome(
            presentation: controller.presentation, language: language,
            videoSurface: AnyView(VideoSurface(onAttach: controller.attach, onDetach: controller.detach)),
            onAction: controller.action)
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
