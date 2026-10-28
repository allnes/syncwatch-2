import AppKit
import SwiftUI

private struct DesignPresentedKey: EnvironmentKey { static let defaultValue = true }
extension EnvironmentValues {
    var designPresented: Bool {
        get { self[DesignPresentedKey.self] }
        set { self[DesignPresentedKey.self] = newValue }
    }
}

/// A native hosting boundary keeps embedded resources attached while a pane is hidden.
/// Unlike a conditional subtree, presentation changes never dismantle the child view.
struct RetainedContent: NSViewRepresentable {
    var content: AnyView
    var presented: Bool
    @Environment(\.self) private var environment
    @Environment(\.designPresented) private var inheritedPresentation

    final class Container: NSView {
        let hosting = NSHostingView(rootView: AnyView(EmptyView()))
        override init(frame: NSRect) {
            super.init(frame: frame)
            addSubview(hosting)
        }
        required init?(coder: NSCoder) { nil }
        override func layout() {
            super.layout()
            hosting.frame = bounds
        }
    }

    func makeNSView(context: Context) -> Container { Container(frame: .zero) }
    func updateNSView(_ view: Container, context: Context) {
        let active = presented && inheritedPresentation
        view.hosting.rootView = AnyView(content.environment(\.self, environment).environment(\.designPresented, active))
        if !active, let focused = view.window?.firstResponder as? NSView, focused.isDescendant(of: view) {
            view.window?.makeFirstResponder(nil)
        }
        view.isHidden = !active
        view.setAccessibilityHidden(!active)
        view.needsLayout = true
    }
}
