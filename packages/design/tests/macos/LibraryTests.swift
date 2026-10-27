import AppKit
import SwiftUI
import Testing

@testable import SyncWatchDesign

@Test func libraryCapabilitiesRejectUnavailableAndStaleActions() {
    var events: [String] = []
    let receive: (String, String?) -> Void = { action, value in events.append(action + ":" + (value ?? "")) }
    LibraryPresentation().dispatch("chooseFolder", to: receive)
    for state in LibraryVisualState.allCases {
        let presentation = LibraryPresentation.gallery(state)
        presentation.dispatch("openCall", to: receive)
        presentation.dispatch("selectMovie", value: "removed-id", to: receive)
        presentation.dispatch("startWatching", to: receive)
    }
    #expect(events == ["startWatching:"])
    let scanning = LibraryPresentation.gallery(.scanning)
    scanning.dispatch("search", value: "film", to: receive)
    var selected = LibraryPresentation.gallery(.selected)
    selected.dispatch("selectMovie", value: "1", to: receive)
    selected.selectedID = "removed-id"
    selected.dispatch("startWatching", to: receive)
    selected.enabledActions.insert("unregistered")
    selected.dispatch("unregistered", to: receive)
    #expect(events == ["startWatching:", "selectMovie:1"])
    #expect(SyncWatchCopy.text("library", language: "ru") == "Библиотека фильмов")
    #expect(SyncWatchCopy.text("library", language: "unknown") == SyncWatchCopy.text("library"))
    #expect(SyncWatchCopy.text("unknown-key", language: "ru") == "unknown-key")
    #expect(LibraryVisualState.allCases.map(\.rawValue) == SyncWatchCopy.galleryStates)
}

/// No windows are opened. Safe for headless CI and a locked workstation.
@MainActor @Test func renderLibraryStateThemeLanguageAndViewportMatrix() throws {
    NSApplication.shared.setActivationPolicy(.prohibited)
    let destination = ProcessInfo.processInfo.environment["SYNCWATCH_DESIGN_SCREENSHOTS"].map {
        URL(fileURLWithPath: $0, isDirectory: true)
    }
    if let destination { try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true) }
    for state in LibraryVisualState.allCases {
        for (name, scheme) in [("dark", ColorScheme.dark), ("light", ColorScheme.light)] {
            for language in ["en", "ru"] {
                for (width, height) in [(1120, 760), (800, 600)] {
                    // Include the long filename rather than only the shortest gallery row.
                    var presentation = LibraryPresentation.gallery(state)
                    if !presentation.entries.isEmpty { presentation.selectedID = "1" }
                    let view = LibraryWorkspace(presentation: presentation, language: language)
                        .environment(\.colorScheme, scheme).frame(width: CGFloat(width), height: CGFloat(height))
                    let hosting = NSHostingView(rootView: view)
                    hosting.frame = NSRect(x: 0, y: 0, width: width, height: height)
                    let window = NSWindow(
                        contentRect: hosting.frame, styleMask: [.borderless], backing: .buffered, defer: false)
                    window.isReleasedWhenClosed = false
                    window.contentView = hosting
                    hosting.layoutSubtreeIfNeeded()
                    let bitmap = try #require(hosting.bitmapImageRepForCachingDisplay(in: hosting.bounds))
                    hosting.cacheDisplay(in: hosting.bounds, to: bitmap)
                    #expect(bitmap.pixelsWide >= width && bitmap.pixelsHigh >= height)
                    #expect(!window.isVisible)
                    defer { window.close() }
                    let background = try #require(bitmap.colorAt(x: 0, y: 0))
                    let panel = try #require(bitmap.colorAt(x: 30, y: 30))
                    #expect(background.alphaComponent > 0.99 && panel.alphaComponent > 0.99)
                    #expect(background != panel)
                    if let destination {
                        let data = try #require(bitmap.representation(using: .png, properties: [:]))
                        try data.write(
                            to: destination.appendingPathComponent(
                                "\(state.rawValue)-\(name)-\(language)-\(width)x\(height).png"))
                    }
                }
            }
        }
    }
}

private struct MetadataCorpus: Decodable {
    struct Case: Decodable {
        let language: String
        let durationMs: Int64?
        let width: Int
        let height: Int
        let audioTracks: Int?
        let subtitleTracks: Int?
        let expected: [String: String]
    }
    let cases: [Case]
}

@Test func libraryMetadataUsesSharedPresentationCorpus() throws {
    let fixture = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("fixtures/library-metadata.json")
    let corpus = try JSONDecoder().decode(MetadataCorpus.self, from: Data(contentsOf: fixture))
    for row in corpus.cases {
        var p = LibraryPresentation.gallery(.selected)
        p.metadataDurationMs = row.durationMs
        p.metadataWidth = row.width
        p.metadataHeight = row.height
        p.metadataAudioTracks = row.audioTracks
        p.metadataSubtitleTracks = row.subtitleTracks
        let context = DesignBindings.library(p, query: "", language: row.language)
        for (key, value) in row.expected { #expect(context.values[key] == value) }
    }
}
