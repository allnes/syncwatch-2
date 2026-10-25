import AppKit
import SwiftUI
import Testing

@testable import SyncWatchDesign

@MainActor private final class SurfaceLifetime {
    var made = 0
    var dismantled = 0
    var view: NSView?
}
private struct LifetimeSurface: NSViewRepresentable {
    let lifetime: SurfaceLifetime
    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        lifetime.made += 1
        lifetime.view = view
        return view
    }
    func updateNSView(_ view: NSView, context: Context) {}
    func makeCoordinator() -> SurfaceLifetime { lifetime }
    static func dismantleNSView(_ view: NSView, coordinator: SurfaceLifetime) { coordinator.dismantled += 1 }
}

@MainActor @Test func libraryNavigationRetainsTheNativeSurfaceAndHidesItsAncestors() async throws {
    NSApplication.shared.setActivationPolicy(.prohibited)
    let lifetime = SurfaceLifetime()
    let frame = NSRect(x: 0, y: 0, width: 800, height: 600)
    func content(_ playerPresented: Bool) -> ApplicationChrome {
        ApplicationChrome(
            playerPresented: playerPresented, library: AnyView(Color.yellow),
            player: AnyView(LifetimeSurface(lifetime: lifetime)))
    }
    let hosting = NSHostingView(rootView: content(true))
    let window = NSWindow(contentRect: frame, styleMask: [.borderless], backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false
    window.contentView = hosting
    defer { window.close() }
    for presented in [true, false, true, false, true] {
        hosting.rootView = content(presented)
        hosting.frame = frame
        hosting.layoutSubtreeIfNeeded()
        try await Task.sleep(for: .milliseconds(20))
        hosting.layoutSubtreeIfNeeded()
        let view = try #require(lifetime.view)
        #expect(view.window === window)
        #expect(view.isHiddenOrHasHiddenAncestor == !presented)
        #expect(view.bounds.width > 0 && view.bounds.height > 0)
        #expect(lifetime.made == 1 && lifetime.dismantled == 0)
        #expect(!window.isVisible)
    }
}
