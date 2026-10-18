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
                "tests", "generated/windows", "generated/linux", "tokens", "themes.json", "components.json",
                "copy.json", "package.json", "windows", "linux", "generated/design-manifest.json",
            ],
            sources: ["generated/apple", "apple"]),
        .testTarget(name: "SyncWatchDesignTests", dependencies: ["SyncWatchDesign"], path: "tests/apple"),
    ]
)
