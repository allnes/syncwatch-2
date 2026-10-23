import AppKit
import Foundation
import SwiftUI
import Testing

@testable import SyncWatchDesign

private struct Manifest: Decodable {
    struct Token: Decodable {
        let id: String
        let type: String
        let value: Value
    }

    enum Value: Decodable {
        case color(String)
        case dimension(Double)

        init(from decoder: any Decoder) throws {
            let container = try decoder.singleValueContainer()
            if let value = try? container.decode(String.self) {
                self = .color(value)
            } else {
                self = .dimension(try container.decode(Double.self))
            }
        }
    }

    let tokens: [Token]
    let themes: [String: [String: String]]
}

private func manifest() throws -> Manifest {
    let directory = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent()
    return try JSONDecoder().decode(
        Manifest.self, from: Data(contentsOf: directory.appendingPathComponent("generated/design-manifest.json")))
}

private func verifyColor(_ color: Color, hex: String) throws {
    let native = try #require(NSColor(color).usingColorSpace(.sRGB))
    let value = try #require(UInt32(hex.dropFirst(), radix: 16))
    let actual = [native.redComponent, native.greenComponent, native.blueComponent, native.alphaComponent]
    for (index, shift) in [24, 16, 8, 0].enumerated() {
        #expect(abs(Double(actual[index]) - Double((value >> shift) & 255) / 255) < 0.000001)
    }
}

@Test func nativeValuesMatchEveryManifestToken() throws {
    let tokens = try manifest().tokens
    #expect(SyncWatchTokens.colors.count + SyncWatchTokens.dimensions.count == tokens.count)
    for token in tokens {
        switch token.value {
        case .color(let hex):
            #expect(token.type == "color")
            try verifyColor(#require(SyncWatchTokens.colors[token.id]), hex: hex)
        case .dimension(let value):
            #expect(token.type == "number")
            #expect(try #require(SyncWatchTokens.dimensions[token.id]) == value)
        }
    }
}

@Test func everyThemeRoleResolvesToTheDeclaredNativeColor() throws {
    let source = try manifest()
    for (name, scheme) in [("dark", ColorScheme.dark), ("light", ColorScheme.light)] {
        let roles = try #require(source.themes[name])
        let theme = SyncWatchTheme.resolve(scheme)
        let properties = Mirror(reflecting: theme).children
        #expect(properties.count == roles.count)
        for property in properties {
            let role = try #require(property.label)
            let id = try #require(roles[role])
            let token = try #require(source.tokens.first { $0.id == id })
            guard case .color(let hex) = token.value else {
                Issue.record("Theme role is not a color")
                continue
            }
            try verifyColor(#require(property.value as? Color), hex: hex)
        }
    }
}
