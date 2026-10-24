import AppKit
import SwiftUI
import Testing

@testable import SyncWatchDesign

private struct LayoutProbeCases: Decodable {
    struct Case: Decodable {
        struct Probe: Decodable {
            let x: Int
            let y: Int
            let color: String
        }
        struct InkRegion: Decodable {
            let x: Int
            let y: Int
            let width: Int
            let height: Int
            let present: Bool
        }
        let name: String
        let root: DesignNode
        let width: Int
        let height: Int
        let probes: [Probe]
        let inkRegions: [InkRegion]?
    }
    let cases: [Case]
}

/// The same data changes axis, child order and spacing in the actual primitive renderer.
@MainActor @Test func declarativeCompositionControlsNativeGeometry() throws {
    NSApplication.shared.setActivationPolicy(.prohibited)
    let path = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("fixtures/layout-probes.json")
    let fixture = try JSONDecoder().decode(LayoutProbeCases.self, from: Data(contentsOf: path))
    #expect(fixture.cases.count == 6)
    for item in fixture.cases {
        let frame = NSRect(x: 0, y: 0, width: item.width, height: item.height)
        let host = NSHostingView(rootView: DesignSurface(testingNode: item.root))
        host.frame = frame
        let window = NSWindow(contentRect: frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        defer { window.close() }
        let bitmap = try #require(host.bitmapImageRepForCachingDisplay(in: host.bounds))
        host.cacheDisplay(in: host.bounds, to: bitmap)
        #expect(!window.isVisible)
        let scale = Double(bitmap.pixelsWide) / Double(item.width)
        for probe in item.probes {
            let c = try #require(
                bitmap.colorAt(x: Int(Double(probe.x) * scale), y: Int(Double(probe.y) * scale))?.usingColorSpace(.sRGB)
            )
            switch probe.color {
            case "cyan": #expect(c.blueComponent > c.redComponent + 0.2, "\(item.name)")
            case "yellow": #expect(c.redComponent > c.blueComponent + 0.2, "\(item.name)")
            default: #expect(c.redComponent < 0.01 && c.greenComponent < 0.01 && c.blueComponent < 0.01, "\(item.name)")
            }
        }
        for region in item.inkRegions ?? [] {
            var found = false
            for y in region.y..<(region.y + region.height) {
                for x in region.x..<(region.x + region.width) {
                    let c = try #require(
                        bitmap.colorAt(x: Int(Double(x) * scale), y: Int(Double(y) * scale))?.usingColorSpace(.sRGB))
                    if c.blueComponent > c.redComponent + 0.2 { found = true }
                }
            }
            #expect(found == region.present, "\(item.name): paragraph ink in \(region.x),\(region.y)")
        }
    }
}
