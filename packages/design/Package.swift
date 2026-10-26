// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "SyncWatchDesign",
    platforms: [.macOS(.v13)],
    products: [.library(name: "SyncWatchDesign", targets: ["SyncWatchDesign"])],
    targets: [
        .target(
            name: "SyncWatchDesign", path: ".",
            exclude: [
                "tests", "LICENSE", "README.md", "generated/windows", "generated/linux", "tokens", "themes.json",
                "components.json", "layouts.json", "call.json", "selection-menu.json",
                "copy.json", "settings.json", "room.json", "player.json", "player-settings.json", "package.json",
                "windows", "linux",
                "generated/design-manifest.json",
            ],
            sources: ["generated/macos", "macos"]),
        .testTarget(name: "SyncWatchDesignTests", dependencies: ["SyncWatchDesign"], path: "tests/macos"),
    ]
)
