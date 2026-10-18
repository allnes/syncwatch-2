import AppKit
import SwiftUI
import Testing

@testable import SyncWatchDesign

@Test func settingsDraftRequiresValidCapabilitiesAndPersistenceAcknowledgement() {
    var editor = SettingsEditor(editableFields: ["theme", "language"], canSave: true)
    editor.edit("folder", value: "ignored")
    editor.edit("unregistered", value: "ignored")
    #expect(editor.values["folder"] == "" && editor.values["unregistered"] == nil)
    editor.edit("theme", value: "invalid")
    var writes = 0
    #expect(
        !editor.save { _ in
            writes += 1
            return true
        })
    #expect(writes == 0 && editor.state == .invalidConfiguration)
    editor.cancel()
    #expect(editor.values["theme"] == "system")
    editor.edit("theme", value: "dark")
    #expect(!editor.save { _ in false })
    #expect(editor.state == .invalidConfiguration && editor.message == "saveFailed")
    #expect(
        editor.save { values in
            writes += 1
            return values["theme"] == "dark"
        })
    #expect(editor.state == .savedNotice && writes == 1)
    editor.edit("theme", value: "light")
    editor.cancel()
    #expect(editor.values["theme"] == "dark")
    var readonly = SettingsEditor()
    #expect(
        !readonly.save { _ in
            writes += 1
            return true
        })
    #expect(writes == 1)
    let invalid = SettingsEditor(values: ["unexpected": "value"], canSave: true)
    #expect(!invalid.isValid)
    #expect(SettingsVisualState.allCases.map(\.rawValue) == SyncWatchSettings.states)
}

@MainActor @Test func renderAllSettingsSectionsStatesThemesAndLanguages() throws {
    NSApplication.shared.setActivationPolicy(.prohibited)
    let output = ProcessInfo.processInfo.environment["SYNCWATCH_DESIGN_SCREENSHOTS"].map {
        URL(fileURLWithPath: $0, isDirectory: true)
    }
    if let output { try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true) }
    for section in SyncWatchSettings.sections {
        for state in SettingsVisualState.allCases {
            for (name, scheme) in [("dark", ColorScheme.dark), ("light", ColorScheme.light)] {
                for language in ["en", "ru"] {
                    let editor = SettingsEditor(
                        editableFields: Set(SyncWatchSettings.defaults.keys), canSave: true, state: state)
                    let view = SettingsDialog(editor: .constant(editor), language: language, section: section)
                        .environment(\.colorScheme, scheme)
                    let frame = NSRect(x: 0, y: 0, width: 680, height: 420)
                    let hosting = NSHostingView(rootView: view)
                    hosting.frame = frame
                    let window = NSWindow(
                        contentRect: frame, styleMask: [.borderless], backing: .buffered, defer: false)
                    window.isReleasedWhenClosed = false
                    window.contentView = hosting
                    hosting.layoutSubtreeIfNeeded()
                    let bitmap = try #require(hosting.bitmapImageRepForCachingDisplay(in: hosting.bounds))
                    hosting.cacheDisplay(in: hosting.bounds, to: bitmap)
                    #expect(!window.isVisible)
                    #expect(try #require(bitmap.colorAt(x: 40, y: 40)).alphaComponent > 0.99)
                    defer { window.close() }
                    if let output {
                        let data = try #require(bitmap.representation(using: .png, properties: [:]))
                        let filename = "settings\(section)\(state.rawValue)-\(name)-\(language)-680x420.png"
                        try data.write(to: output.appendingPathComponent(filename))
                    }
                }
            }
        }
    }
}
