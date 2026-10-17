import AppKit
import SwiftUI
import SyncWatchDesign
import SyncWatchDomain

@main
struct SyncWatchApp: App {
    private let playbackScope = PlaybackScope.fresh()

    var body: some Scene {
        Window("SyncWatch", id: "main") {
            ShellView()
        }
        .defaultSize(width: 1120, height: 760)
    }
}

private struct ShellView: View {
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let theme = SyncWatchTheme.resolve(colorScheme)
        Text("SyncWatch")
            .font(.largeTitle)
            .foregroundStyle(theme.text)
            .padding(SyncWatchTokens.layoutWorkspacePadding)
            .frame(minWidth: 800, minHeight: 600)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(theme.background)
            .tint(theme.accent)
    }
}
