// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "SyncWatchApple",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "SyncWatch", targets: ["SyncWatch"])],
    dependencies: [
        .package(path: "../../packages/apple-domain"),
        .package(path: "../../packages/design"),
        .package(path: "../../packages/apple-playback"),
    ],
    targets: [
        .executableTarget(
            name: "SyncWatch",
            dependencies: [
                .product(name: "SyncWatchDomain", package: "apple-domain"),
                .product(name: "SyncWatchDesign", package: "design"),
                .product(name: "SyncWatchPlayback", package: "apple-playback"),
            ]
        ),
        .testTarget(name: "SyncWatchTests", dependencies: ["SyncWatch"]),
    ]
)
