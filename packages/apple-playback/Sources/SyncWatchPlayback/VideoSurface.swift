import AppKit
import SwiftUI

/// Surface lifetime only. Geometry and appearance belong to the design's video slot.
public struct VideoSurface: NSViewRepresentable {
    public final class View: NSView {
        var attach: (@MainActor (NSView) -> Void)?
        var attached = false
        public override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            if window != nil && !attached {
                attached = true
                attach?(self)
            }
        }
    }
    public final class Coordinator {
        let detach: @MainActor (NSView) -> Void
        init(detach: @escaping @MainActor (NSView) -> Void) { self.detach = detach }
    }
    private let attach: @MainActor (NSView) -> Void
    private let detach: @MainActor (NSView) -> Void
    public init(
        onAttach: @escaping @MainActor (NSView) -> Void,
        onDetach: @escaping @MainActor (NSView) -> Void
    ) {
        attach = onAttach
        detach = onDetach
    }
    public func makeCoordinator() -> Coordinator { Coordinator(detach: detach) }
    public func makeNSView(context: Context) -> View {
        let view = View(frame: .zero)
        view.attach = attach
        return view
    }
    public func updateNSView(_ nsView: View, context: Context) {}
    public static func dismantleNSView(_ nsView: View, coordinator: Coordinator) {
        nsView.attach = nil
        if nsView.attached { coordinator.detach(nsView) }
    }
}
