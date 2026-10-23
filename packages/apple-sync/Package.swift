// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "SyncWatchSynchronization",
    platforms: [.macOS(.v13)],
    products: [.library(name: "SyncWatchSynchronization", targets: ["SyncWatchSynchronization"])],
    dependencies: [.package(path: "../apple-domain"), .package(path: "../apple-bridge")],
    targets: [
        .target(
            name: "SyncWatchSynchronization",
            dependencies: [
                .product(name: "SyncWatchDomain", package: "apple-domain"),
                .product(name: "SyncWatchBridge", package: "apple-bridge"),
            ]),
        .testTarget(name: "SyncWatchSynchronizationTests", dependencies: ["SyncWatchSynchronization"]),
    ]
)
