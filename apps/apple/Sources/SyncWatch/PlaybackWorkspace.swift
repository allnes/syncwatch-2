import AppKit
import SwiftUI
import SyncWatchDesign
import SyncWatchDomain
import SyncWatchPlayback

/// Explicit local development entry; room/watch capabilities remain with their coordinator.
struct LocalPlaybackLaunch {
    let file: URL
    let package: URL
    static func read(_ arguments: [String] = CommandLine.arguments) -> Self? {
        guard let index = arguments.firstIndex(of: "--local-playback"), index + 1 < arguments.count else { return nil }
        let package: URL
        if let i = arguments.firstIndex(of: "--media-package"), i + 1 < arguments.count {
            package = URL(filePath: arguments[i + 1])
        } else {
            package = Bundle.main.bundleURL.appendingPathComponent("Contents/Frameworks/Media")
        }
        return Self(file: URL(filePath: arguments[index + 1]), package: package)
    }
}

@MainActor final class PlaybackController: ObservableObject {
    @Published private(set) var presentation = PlayerPresentation()
    @Published private(set) var failed = false
    let player = VLCPlayback()
    private(set) var scope = PlaybackScope.fresh()
    private let launch: LocalPlaybackLaunch
    private var polling: Task<Void, Never>?
    private var view: NSView?
    private var window: NSWindow?
    private var closing = false
    private var closed = false

    init(launch: LocalPlaybackLaunch) {
        self.launch = launch
        presentation.title = launch.file.lastPathComponent
        presentation.enabledActions = ["endWatching", "toggleFullscreen"]
    }
    func attach(_ view: NSView) {
        guard self.view == nil, !closing else { return }
        self.view = view
        window = view.window
        polling = Task { [self] in
            do {
                scope = try scope.replacingMedia()
                let address = UInt(bitPattern: Unmanaged.passUnretained(view).toOpaque())
                try await player.open(package: launch.package, appKitSurfaceAddress: address)
                try Task.checkCancellation()
                try await player.load(launch.file, scope: scope)
                while !Task.isCancelled {
                    let observation = try await player.observe(scope)
                    guard !closing else { break }
                    apply(observation)
                    try await Task.sleep(for: .milliseconds(100))
                }
            } catch is CancellationError {
            } catch {
                if !closing {
                    failed = true
                    presentation.enabledActions = ["endWatching"]
                }
            }
        }
    }
    private func apply(_ value: PlaybackObservation) {
        if value.status == .failed {
            failed = true
            presentation.enabledActions = ["endWatching"]
            return
        }
        presentation.state =
            value.ended
            ? .ended
            : value.buffering ? .buffering : value.status != .ready ? .loading : value.paused ? .paused : .playing
        presentation.positionMs = value.positionMs
        presentation.durationMs = value.durationMs ?? 0
        presentation.volume = value.volume ?? presentation.volume
        presentation.muted = value.muted
        presentation.enabledActions = ["endWatching", "toggleFullscreen", "playPause"]
        if value.volume != nil { presentation.enabledActions.formUnion(["setMovieVolume", "muteMovie"]) }
        if value.seekable { presentation.enabledActions.formUnion(["seek", "skip"]) }
    }
    func action(_ action: String, value: Double?) {
        guard !closing else { return }
        if action == "endWatching" {
            let ownedWindow = window
            Task {
                await close()
                ownedWindow?.close()
            }
            return
        }
        if action == "toggleFullscreen" {
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
        closed = true
    }
}

struct PlaybackWorkspace: View {
    @StateObject private var controller: PlaybackController
    @StateObject private var preferences = AppearancePreferences(
        store: FileLocalStateStore(url: AppearancePreferences.defaultURL))
    init(launch: LocalPlaybackLaunch) { _controller = StateObject(wrappedValue: PlaybackController(launch: launch)) }
    var body: some View {
        PlayerChrome(
            presentation: controller.presentation,
            language: preferences.state.preferences.language,
            videoSurface: AnyView(VideoSurface(onAttach: controller.attach, onDetach: controller.detach)),
            onAction: controller.action
        )
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
