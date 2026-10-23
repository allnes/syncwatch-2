// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "SyncWatchMacOS",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "SyncWatch", targets: ["SyncWatch"])],
    dependencies: [
        .package(path: "../../packages/macos-domain"),
        .package(path: "../../packages/design"),
        .package(path: "../../packages/macos-playback"),
    ],
    targets: [
        .executableTarget(
            name: "SyncWatch",
            dependencies: [
                .product(name: "SyncWatchDomain", package: "macos-domain"),
                .product(name: "SyncWatchDesign", package: "design"),
                .product(name: "SyncWatchPlayback", package: "macos-playback"),
            ]
        ),
        .testTarget(name: "SyncWatchTests", dependencies: ["SyncWatch"]),
    ]
)
