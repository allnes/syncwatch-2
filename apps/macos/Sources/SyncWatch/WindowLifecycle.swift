import AppKit
import SwiftUI

@MainActor final class ApplicationLifecycle: NSObject, NSApplicationDelegate {
    /// Native termination may enter a nested run loop. Leave the current MainActor/GCD job first.
    static func afterCurrentEvent(_ operation: @escaping @MainActor @Sendable () -> Void) {
        RunLoop.main.perform(inModes: [.common]) { MainActor.assumeIsolated { operation() } }
    }
    var prepareForTermination: (@MainActor () async -> Void)?
    private var terminating = false
    private var terminationPrepared = false
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if terminationPrepared { return .terminateNow }
        guard let prepareForTermination else { return .terminateNow }
        guard !terminating else { return .terminateLater }
        terminating = true
        Task {
            await prepareForTermination()
            terminationPrepared = true
            Self.afterCurrentEvent { sender.reply(toApplicationShouldTerminate: true) }
        }
        return .terminateLater
    }
}

/// NSObject signature queries are nonisolated; the weak delegate reference is lock protected.
private final class WindowDelegateTarget: @unchecked Sendable {
    private let lock = NSLock()
    private weak var value: (any NSWindowDelegate)?
    func set(_ delegate: (any NSWindowDelegate)?) { lock.withLock { value = delegate } }
    func get() -> (any NSWindowDelegate)? { lock.withLock { value } }
}

/// Native lifetime only. Keep the window and its descendants until asynchronous teardown completes.
@MainActor struct WindowCloseGate: NSViewRepresentable {
    let close: @MainActor () async -> Void
    final class View: NSView {
        var moved: ((NSWindow) -> Void)?
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            if let window { moved?(window) }
        }
    }
    @MainActor final class Coordinator: NSObject, NSWindowDelegate {
        var close: @MainActor () async -> Void
        private weak var window: NSWindow?
        private var previous: (any NSWindowDelegate)?
        private nonisolated let target = WindowDelegateTarget()
        private var pending = false
        private var released = false
        init(close: @escaping @MainActor () async -> Void) { self.close = close }
        func attach(_ window: NSWindow) {
            guard self.window !== window else { return }
            restore()
            self.window = window
            previous = window.delegate
            target.set(previous)
            window.delegate = self
        }
        func restore() {
            if let window, window.delegate === self { window.delegate = previous }
            window = nil
            previous = nil
            target.set(nil)
        }
        func windowShouldClose(_ sender: NSWindow) -> Bool {
            if released { return previous?.windowShouldClose?(sender) ?? true }
            guard !pending else { return false }
            pending = true
            Task { [self, sender] in
                await close()
                released = true
                pending = false
                ApplicationLifecycle.afterCurrentEvent { sender.performClose(nil) }
            }
            return false
        }
        nonisolated override func responds(to selector: Selector!) -> Bool {
            super.responds(to: selector) || target.get()?.responds(to: selector) == true
        }
        nonisolated override func forwardingTarget(for selector: Selector!) -> Any? {
            if let delegate = target.get(), delegate.responds(to: selector) { return delegate }
            return super.forwardingTarget(for: selector)
        }
    }
    func makeCoordinator() -> Coordinator { Coordinator(close: close) }
    func makeNSView(context: Context) -> View {
        let view = View(frame: .zero)
        view.moved = { [coordinator = context.coordinator] in coordinator.attach($0) }
        return view
    }
    func updateNSView(_ view: View, context: Context) {
        context.coordinator.close = close
        if let window = view.window { context.coordinator.attach(window) }
    }
    static func dismantleNSView(_ view: View, coordinator: Coordinator) {
        view.moved = nil
        coordinator.restore()
    }
}
