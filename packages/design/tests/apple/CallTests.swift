import AppKit
import SwiftUI
import Testing

@testable import SyncWatchDesign

private struct CallInput: Decodable {
    let action: String
    let values: [Double]
    var request: CallRequest { CallRequest(action, values) }
}
private struct CallCase: Decodable {
    let name: String
    let state: String
    let preview: String
    let joined: Bool?
    let microphoneEnabled: Bool?
    let cameraEnabled: Bool?
    let volume: Double?
    let enabledActions: [String]
    let requests: [CallInput]
    let expected: [CallInput]
    let showsRemote: Bool
    let showsLocal: Bool
}
private struct CallCases: Decodable { let cases: [CallCase] }

@Test func callRequestsRequireMembershipObservationsAndCapabilities() throws {
    let source = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("fixtures/call-actions.json")
    let corpus = try JSONDecoder().decode(CallCases.self, from: Data(contentsOf: source))
    #expect(corpus.cases.count == 45)
    for item in corpus.cases {
        var p = CallPresentation()
        p.state = try #require(CallVisualState(rawValue: item.state))
        p.preview = try #require(CallPreviewState(rawValue: item.preview))
        p.joined = item.joined
        p.microphoneEnabled = item.microphoneEnabled
        p.cameraEnabled = item.cameraEnabled
        p.volume = item.volume
        p.enabledActions = Set(item.enabledActions)
        var events: [CallRequest] = []
        for input in item.requests { p.dispatch(input.request) { events.append($0) } }
        #expect(events == item.expected.map(\.request), "\(item.name)")
        #expect(p.state.rawValue == item.state && p.joined == item.joined && p.volume == item.volume)
        #expect(p.showsRemoteSurface == item.showsRemote && p.showsLocalPreview == item.showsLocal, "\(item.name)")
        #expect(p.previewLabel(hasSurface: false) != "cameraActive")
        #expect((0...1).contains(p.displayedVolume))
    }
    var ready = CallPresentation.gallery(SyncWatchCall.galleryCases[2])
    var count = 0
    for value in [Double.nan, .infinity, -.infinity] {
        for request in [
            CallRequest("move", [value, 0]), CallRequest("resize", [300, value]),
            CallRequest("setCallVolume", [value]), CallRequest("setCameraEnabled", [value]),
        ] {
            ready.dispatch(request) { _ in count += 1 }
        }
        ready.volume = value
        #expect(!ready.allows("setCallVolume") && ready.displayedVolume == 0)
    }
    #expect(count == 0)
    #expect(CallVisualState.allCases.map(\.rawValue) == SyncWatchCall.states)
    #expect(CallPreviewState.allCases.map(\.rawValue) == SyncWatchCall.previewStates)
}

/// Offscreen snapshots only; no provider, camera, browser or physical desktop capture.
@MainActor @Test func renderCallStatePreviewThemeLanguageAndViewportMatrix() throws {
    NSApplication.shared.setActivationPolicy(.prohibited)
    let output = ProcessInfo.processInfo.environment["SYNCWATCH_DESIGN_SCREENSHOTS"].map {
        URL(fileURLWithPath: $0, isDirectory: true)
    }
    if let output { try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true) }
    var emitted = 0
    for item in SyncWatchCall.galleryCases {
        for (name, scheme) in [("dark", ColorScheme.dark), ("light", ColorScheme.light)] {
            for language in ["en", "ru"] {
                for (width, height) in [(300, 210), (420, 300)] {
                    let p = CallPresentation.gallery(item)
                    let view = CallWindowShell(
                        presentation: p, language: language,
                        remoteSurface: AnyView(Color.green), localPreview: AnyView(Color.blue)
                    ) { _ in emitted += 1 }
                    .environment(\.colorScheme, scheme).frame(width: CGFloat(width), height: CGFloat(height))
                    let frame = NSRect(x: 0, y: 0, width: width, height: height)
                    let hosting = NSHostingView(rootView: view)
                    hosting.frame = frame
                    let window = NSWindow(
                        contentRect: frame, styleMask: [.borderless], backing: .buffered, defer: false)
                    window.isReleasedWhenClosed = false
                    window.contentView = hosting
                    hosting.layoutSubtreeIfNeeded()
                    defer { window.close() }
                    let bitmap = try #require(hosting.bitmapImageRepForCachingDisplay(in: hosting.bounds))
                    hosting.cacheDisplay(in: hosting.bounds, to: bitmap)
                    #expect(!window.isVisible && emitted == 0)
                    let scale = CGFloat(bitmap.pixelsWide) / CGFloat(width)
                    let remote = try #require(
                        bitmap.colorAt(x: Int(CGFloat(width - 20) * scale), y: Int(110 * scale))?.usingColorSpace(.sRGB)
                    )
                    #expect(p.showsRemoteSurface ? remote.greenComponent > 0.4 : remote.greenComponent < 0.01)
                    let preview = try #require(
                        bitmap.colorAt(x: Int(16 * scale), y: Int(48 * scale))?.usingColorSpace(.sRGB))
                    #expect(
                        p.showsLocalPreview
                            ? preview.blueComponent > preview.redComponent + 0.3
                            : preview.blueComponent < preview.redComponent + 0.3)
                    if let output {
                        try #require(bitmap.representation(using: .png, properties: [:])).write(
                            to: output.appendingPathComponent(
                                "call\(item.id)-\(name)-\(language)-\(width)x\(height).png"))
                    }
                }
            }
        }
    }
}
