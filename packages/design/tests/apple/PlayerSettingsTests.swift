import AppKit
import SwiftUI
import Testing

@testable import SyncWatchDesign

private struct PlayerSettingCases: Decodable {
    struct Field: Decodable {
        let id: String
        let valid: [String]
        let invalid: [String]
    }
    let fields: [Field]
}

@Test func playerSettingsRejectInvalidInputsAndPublishOnlyAcknowledgedSnapshots() throws {
    let source = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("fixtures/player-settings.json")
    let fixtures = try JSONDecoder().decode(PlayerSettingCases.self, from: Data(contentsOf: source))
    #expect(Set(fixtures.fields.map(\.id)) == Set(SyncWatchPlayerSettings.defaults.keys))
    for fixture in fixtures.fields {
        let field = try #require(SyncWatchPlayerSettings.fields.first { $0.id == fixture.id })
        for value in fixture.valid { #expect(PlayerSettingsEditor.valid(value, for: field), "\(field.id): \(value)") }
        for value in fixture.invalid {
            #expect(!PlayerSettingsEditor.valid(value, for: field), "\(field.id): \(value)")
        }
    }
    var editor = PlayerSettingsEditor(editableFields: Set(SyncWatchPlayerSettings.defaults.keys), canSave: true)
    #expect(editor.isValid)
    editor.edit("brightness", value: "0.35")
    editor.edit("subtitleSize", value: "36")
    editor.reset("image")
    #expect(editor.values["brightness"] == "0" && editor.values["subtitleSize"] == "36")
    editor.edit("unknown", value: "ignored")
    #expect(editor.values["unknown"] == nil)
    editor.edit("cursorDelay", value: "NaN")
    var writes = 0
    #expect(
        !editor.save { _ in
            writes += 1
            return true
        } && writes == 0)
    editor.cancel()
    editor.edit("skipSeconds", value: "30")
    #expect(!editor.save { _ in false } && editor.message == "saveFailed")
    #expect(editor.values["skipSeconds"] == "30")
    var received: [String: String] = [:]
    #expect(
        editor.save {
            received = $0
            writes += 1
            return true
        })
    #expect(editor.state == .savedNotice && editor.message == "changesSaved" && writes == 1)
    editor.edit("skipSeconds", value: "60")
    #expect(received["skipSeconds"] == "30")
    editor.cancel()
    #expect(editor.values["skipSeconds"] == "30")
    var limited = PlayerSettingsEditor(values: ["contrast": "0.5"], editableFields: ["brightness"], canSave: true)
    limited.edit("brightness", value: "0.2")
    limited.edit("contrast", value: "0.4")
    limited.reset("image")
    #expect(limited.values["brightness"] == "0" && limited.values["contrast"] == "0.5")
    #expect(!limited.canReset("audio") && !limited.canReset("unknown"))
    var readonly = PlayerSettingsEditor(editableFields: Set(SyncWatchPlayerSettings.defaults.keys))
    readonly.edit("brightness", value: "0.5")
    readonly.reset("image")
    #expect(readonly.state == .readOnly && readonly.values["brightness"] == "0")
    #expect(
        !readonly.save { _ in
            writes += 1
            return true
        } && writes == 1)
    #expect(!PlayerSettingsEditor(editableFields: ["brightness"], canSave: true, state: .readOnly).allows("brightness"))
    #expect(!PlayerSettingsEditor(values: ["unknown": "value"]).isValid)
    #expect(!PlayerSettingsEditor(editableFields: ["unknown"], canSave: true).isValid)
    #expect(PlayerSettingsEditor.canonical(0.35000000000001) == "0.35")
    #expect(PlayerSettingsEditor.canonical(-0.0) == "0" && PlayerSettingsEditor.canonical(.nan) == "")
    #expect(PlayerSettingsVisualState.allCases.map(\.rawValue) == SyncWatchPlayerSettings.states)
    #expect(PlayerPresentation.gallery(.paused).allows("openPlayerSettings"))
}

@MainActor private func playerSettingsBitmap<V: View>(_ view: V, width: Int = 680, height: Int = 460) throws
    -> NSBitmapImageRep
{
    NSApplication.shared.setActivationPolicy(.prohibited)
    let frame = NSRect(x: 0, y: 0, width: width, height: height)
    let host = NSHostingView(rootView: view)
    host.frame = frame
    let window = NSWindow(contentRect: frame, styleMask: [.borderless], backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false
    window.contentView = host
    host.layoutSubtreeIfNeeded()
    defer { window.close() }
    let bitmap = try #require(host.bitmapImageRepForCachingDisplay(in: host.bounds))
    host.cacheDisplay(in: host.bounds, to: bitmap)
    #expect(!window.isVisible)
    return bitmap
}

@MainActor @Test func subtitlePreviewRendersActualGlyphsAndRespondsToDraftChanges() throws {
    func pixels(_ changes: [String: String]) throws -> (count: Int, y: Double, red: Double, blue: Double) {
        let values = SyncWatchPlayerSettings.defaults.merging(changes) { _, v in v }
        let bitmap = try playerSettingsBitmap(PlayerSubtitlePreview(values: values), width: 440, height: 130)
        var count = 0
        var sumY = 0.0
        var red = 0.0
        var blue = 0.0
        for y in 0..<bitmap.pixelsHigh {
            for x in 0..<bitmap.pixelsWide {
                let color = try #require(bitmap.colorAt(x: x, y: y)?.usingColorSpace(.sRGB))
                if max(color.redComponent, color.greenComponent, color.blueComponent) > 0.3 {
                    count += 1
                    sumY += Double(y) / Double(bitmap.pixelsHigh)
                    red += color.redComponent
                    blue += color.blueComponent
                }
            }
        }
        #expect(count > 100)
        return (count, sumY / Double(max(1, count)), red / Double(max(1, count)), blue / Double(max(1, count)))
    }
    let bottom = try pixels([:])
    let top = try pixels(["subtitlePosition": "top"])
    #expect(bottom.y > top.y + 0.2)
    let larger = try pixels(["subtitleSize": "48"])
    #expect(larger.count > bottom.count)
    let cyan = try pixels(["subtitleColor": "cyan"])
    #expect(cyan.blue > cyan.red + 0.1)
    let invalid = try pixels([
        "subtitleSize": "NaN", "subtitlePadding": "Infinity", "subtitleOffset": "1e9", "subtitleColor": "black",
        "outlineColor": "white", "subtitleFont": "unknown", "subtitlePosition": "unknown",
    ])
    #expect(invalid.count == bottom.count)
}

@MainActor @Test func renderEveryPlayerSettingsSectionStateThemeAndLanguage() throws {
    let output = ProcessInfo.processInfo.environment["SYNCWATCH_DESIGN_SCREENSHOTS"].map {
        URL(fileURLWithPath: $0, isDirectory: true)
    }
    if let output { try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true) }
    for section in SyncWatchPlayerSettings.sections {
        for state in PlayerSettingsVisualState.allCases {
            for (name, scheme) in [("dark", ColorScheme.dark), ("light", ColorScheme.light)] {
                for language in ["en", "ru"] {
                    let editor = PlayerSettingsEditor(
                        editableFields: Set(SyncWatchPlayerSettings.defaults.keys), canSave: state != .readOnly,
                        state: state)
                    let view = PlayerSettingsDialog(editor: .constant(editor), language: language, section: section)
                        .environment(\.colorScheme, scheme)
                    let bitmap = try playerSettingsBitmap(view)
                    let scale = Double(bitmap.pixelsWide) / 680
                    #expect(try #require(bitmap.colorAt(x: Int(10 * scale), y: Int(10 * scale))).alphaComponent > 0.99)
                    if let output {
                        let png = try #require(bitmap.representation(using: .png, properties: [:]))
                        try png.write(
                            to: output.appendingPathComponent(
                                "playersettings\(section)\(state.rawValue)-\(name)-\(language)-680x460.png"))
                    }
                }
            }
        }
    }
}
