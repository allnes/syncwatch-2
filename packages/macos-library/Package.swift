// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "SyncWatchLibrary", platforms: [.macOS(.v13)],
    products: [.library(name: "SyncWatchLibrary", targets: ["SyncWatchLibrary"])],
    targets: [
        .target(name: "SyncWatchLibrary"),
        .testTarget(name: "SyncWatchLibraryTests", dependencies: ["SyncWatchLibrary"]),
    ])
