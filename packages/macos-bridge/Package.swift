// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "SyncWatchBridge",
    platforms: [.macOS(.v13)],
    products: [.library(name: "SyncWatchBridge", targets: ["SyncWatchBridge"])],
    dependencies: [.package(path: "../macos-domain")],
    targets: [
        .target(name: "SyncWatchBridge", dependencies: [.product(name: "SyncWatchDomain", package: "macos-domain")]),
        .executableTarget(name: "BridgeProbe", dependencies: ["SyncWatchBridge"]),
        .testTarget(name: "SyncWatchBridgeTests", dependencies: ["SyncWatchBridge"]),
    ]
)
