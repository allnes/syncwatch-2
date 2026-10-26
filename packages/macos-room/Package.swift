// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "SyncWatchRoom", platforms: [.macOS(.v13)],
    products: [.library(name: "SyncWatchRoom", targets: ["SyncWatchRoom"])],
    dependencies: [.package(path: "../macos-domain")],
    targets: [
        .target(name: "SyncWatchRoom", dependencies: [.product(name: "SyncWatchDomain", package: "macos-domain")]),
        .testTarget(name: "SyncWatchRoomTests", dependencies: ["SyncWatchRoom"]),
    ])
