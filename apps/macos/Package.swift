// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "SyncWatchMacOS",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "SyncWatch", targets: ["SyncWatch"])],
    dependencies: [
        .package(path: "../../packages/macos-domain"),
        .package(path: "../../packages/macos-library"),
        .package(path: "../../packages/design"),
        .package(path: "../../packages/macos-playback"),
        .package(path: "../../packages/macos-bridge"),
    ],
    targets: [
        .executableTarget(
            name: "SyncWatch",
            dependencies: [
                .product(name: "SyncWatchDomain", package: "macos-domain"),
                .product(name: "SyncWatchLibrary", package: "macos-library"),
                .product(name: "SyncWatchDesign", package: "design"),
                .product(name: "SyncWatchPlayback", package: "macos-playback"),
                .product(name: "SyncWatchBridge", package: "macos-bridge"),
            ]
        ),
        .testTarget(name: "SyncWatchTests", dependencies: ["SyncWatch"]),
    ]
)
