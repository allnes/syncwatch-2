// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "SyncWatchDesign",
    platforms: [.macOS(.v13)],
    products: [.library(name: "SyncWatchDesign", targets: ["SyncWatchDesign"])],
    targets: [
        .target(name: "SyncWatchDesign", path: "generated/apple"),
        .testTarget(name: "SyncWatchDesignTests", dependencies: ["SyncWatchDesign"], path: "tests/apple"),
    ]
)
