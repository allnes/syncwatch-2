import AppKit
import SwiftUI
import Testing

@testable import SyncWatchDesign

private struct SelectionCases: Decodable {
    struct Case: Decodable {
        struct Input: Decodable {
            let entryID: String
            let contextToken: String
        }
        let name: String
        let presentation: SelectionMenuPresentation
        let valid: Bool
        let requests: [Input]
        let expected: [SelectionMenuRequest]
    }
    let cases: [Case]
}

@Test func selectionRequestsPreserveIdentityScopeAndObservedSelection() throws {
    let source = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("fixtures/selection-menu.json")
    let corpus = try JSONDecoder().decode(SelectionCases.self, from: Data(contentsOf: source))
    #expect(corpus.cases.count == 28)
    for item in corpus.cases {
        let p = item.presentation
        #expect(p.isValid == item.valid, "\(item.name)")
        var received: [SelectionMenuRequest] = []
        let before = try JSONEncoder().encode(p)
        for input in item.requests {
            p.dispatch(input.entryID, contextToken: input.contextToken) { received.append($0) }
        }
        #expect(received == item.expected, "\(item.name)")
        #expect(try JSONDecoder().decode(SelectionMenuPresentation.self, from: before).selectedID == p.selectedID)
        if p.isValid {
            let tree = try #require(
                DesignTree.resolve(
                    "SelectionMenu", context: SelectionMenuBindings.context(p),
                    viewport: CGSize(width: 420, height: 360)))
            let labels = elements(tree).filter { $0.id.hasSuffix(".selectionLabel") }.map { $0.string("text") }
            #expect(labels == p.entries.map(\.label), "\(item.name): labels remain literal")
        }
    }
    var p = SelectionMenuFixtures.presentation(kind: "playlist", state: "available")
    p.entries = (0..<SyncWatchSelectionMenu.maximumEntries).map { SelectionMenuEntry(id: "item\($0)", label: "Item") }
    #expect(p.isValid)
    p.entries.append(SelectionMenuEntry(id: "extra", label: "Overflow"))
    #expect(!p.isValid)
}

private func elements(_ node: DesignElement) -> [DesignElement] { [node] + node.children.flatMap(elements) }

/// Actual unshown native renders; no provider, preference store or physical desktop capture.
@MainActor @Test func renderSelectionMenuKindStateThemeAndLanguageMatrix() throws {
    NSApplication.shared.setActivationPolicy(.prohibited)
    let width = Int(SyncWatchTokens.layoutSelectionGalleryWidth)
    let height = Int(SyncWatchTokens.layoutSelectionGalleryHeight)
    let output = ProcessInfo.processInfo.environment["SYNCWATCH_DESIGN_SCREENSHOTS"].map {
        URL(fileURLWithPath: $0, isDirectory: true)
    }
    if let output { try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true) }
    var emitted = 0
    for kind in SyncWatchSelectionMenu.kinds {
        for state in SyncWatchSelectionMenu.states {
            for (theme, scheme) in [("dark", ColorScheme.dark), ("light", ColorScheme.light)] {
                for language in ["en", "ru"] {
                    let p = SelectionMenuFixtures.presentation(kind: kind.id, state: state, language: language)
                    let tree = try #require(
                        DesignTree.resolve(
                            "SelectionMenu", context: SelectionMenuBindings.context(p), language: language,
                            viewport: CGSize(width: width, height: height)))
                    let rows = elements(tree).filter { $0.kind == "button" }
                    #expect(rows.count == p.entries.count)
                    #expect(rows.allSatisfy { $0.number("height") == SyncWatchTokens.controlMenuRowHeight })
                    #expect(rows.allSatisfy { !$0.string("label").isEmpty })
                    if state == "readOnly" { #expect(rows.allSatisfy { !$0.flag("enabled") }) }
                    let view = SelectionMenu(presentation: p, language: language) { _ in emitted += 1 }
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
                    if let output {
                        try #require(bitmap.representation(using: .png, properties: [:])).write(
                            to: output.appendingPathComponent(
                                "selection\(kind.id)\(state)-\(theme)-\(language)-\(width)x\(height).png"))
                    }
                }
            }
        }
    }
    let p = SelectionMenuFixtures.presentation(kind: "playlist", state: "longList")
    let tree = try #require(
        DesignTree.resolve(
            "SelectionMenu", context: SelectionMenuBindings.context(p), viewport: CGSize(width: 200, height: 160)))
    let panel = try #require(elements(tree).first { $0.id.hasSuffix(".selectionPanel") })
    #expect(panel.number("width") <= 200 - 2 * SyncWatchTokens.layoutSelectionEdgeInset)
    #expect(panel.number("height") <= 160 - 2 * SyncWatchTokens.layoutSelectionEdgeInset)
}
