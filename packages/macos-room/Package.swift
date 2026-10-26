// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "SyncWatchRoom", platforms: [.macOS(.v13)],
    products: [.library(name: "SyncWatchRoom", targets: ["SyncWatchRoom"])],
    targets: [
        .target(name: "SyncWatchRoom"),
        .testTarget(name: "SyncWatchRoomTests", dependencies: ["SyncWatchRoom"]),
    ])
