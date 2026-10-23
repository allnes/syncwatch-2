// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "SyncWatchPlaybackNative",
    platforms: [.macOS(.v13)],
    products: [.library(name: "SyncWatchPlaybackNative", targets: ["SyncWatchPlaybackNative"])],
    targets: [
        .target(
            name: "SyncWatchPlaybackNative", path: ".", exclude: ["Package.swift"],
            sources: ["src"], publicHeadersPath: "include")
    ],
    cLanguageStandard: .c11
)
