// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "SyncWatchPlayback",
    platforms: [.macOS(.v13)],
    products: [.library(name: "SyncWatchPlayback", targets: ["SyncWatchPlayback"])],
    dependencies: [
        .package(path: "../apple-domain"),
        .package(path: "../playback-native"),
    ],
    targets: [
        .target(
            name: "SyncWatchPlayback",
            dependencies: [
                .product(name: "SyncWatchDomain", package: "apple-domain"),
                .product(name: "SyncWatchPlaybackNative", package: "playback-native"),
            ])
    ]
)
