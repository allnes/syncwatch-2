// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "SyncWatchBridge",
    platforms: [.macOS(.v13)],
    products: [.library(name: "SyncWatchBridge", targets: ["SyncWatchBridge"])],
    targets: [
        .target(name: "SyncWatchBridge"),
        .executableTarget(name: "BridgeProbe", dependencies: ["SyncWatchBridge"]),
    ]
)
