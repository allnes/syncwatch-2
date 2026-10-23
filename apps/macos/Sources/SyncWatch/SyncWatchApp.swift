import AppKit
import SwiftUI
import SyncWatchDesign
import SyncWatchDomain

@main
struct SyncWatchApp: App {
    private let playbackScope = PlaybackScope.fresh()

    var body: some Scene {
        Window("SyncWatch", id: "main") {
            if let playback = LocalPlaybackLaunch.read() {
                PlaybackWorkspace(launch: playback)
            } else if CommandLine.arguments.contains("--selection-menu-gallery") {
                SelectionMenuGallery()
            } else if CommandLine.arguments.contains("--call-gallery") {
                CallGallery()
            } else if CommandLine.arguments.contains("--player-settings-gallery") {
                PlayerSettingsGallery()
            } else if CommandLine.arguments.contains("--player-gallery") {
                PlayerGallery()
            } else if CommandLine.arguments.contains("--settings-gallery") {
                SettingsGallery()
            } else if CommandLine.arguments.contains("--design-gallery") {
                DesignGallery()
            } else {
                ApplicationWorkspace()
            }
        }
        .defaultSize(width: SyncWatchTokens.layoutGalleryWidth, height: SyncWatchTokens.layoutGalleryHeight)
    }
}
