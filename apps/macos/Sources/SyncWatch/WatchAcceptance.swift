import AppKit
import Foundation
import SyncWatchDomain

/// Explicit application-owned integration check. It does not establish manual or physical acceptance.
@MainActor enum WatchAcceptance {
    private enum Failure: Error { case condition, timeout }
    static var requested: Bool { CommandLine.arguments.contains("--watch-check-report") }
    private static func require(_ value: Bool) throws { if !value { throw Failure.condition } }
    private static func until(_ predicate: @MainActor () async throws -> Bool) async throws {
        let deadline = ContinuousClock.now.advanced(by: .seconds(20))
        while ContinuousClock.now < deadline {
            if try await predicate() { return }
            try await Task.sleep(for: .milliseconds(40))
        }
        throw Failure.timeout
    }
    static func run(preferences: AppearancePreferences, library: LibraryController, watch: WatchSessionCoordinator)
        async
    {
        guard requested else { return }
        let arguments = CommandLine.arguments
        func value(_ flag: String) -> String? {
            arguments.firstIndex(of: flag).flatMap { $0 + 1 < arguments.count ? arguments[$0 + 1] : nil }
        }
        let mode = value("--watch-check-mode") ?? "normal"
        guard let path = value("--watch-check-report"), let file = value("--watch-check-media"),
            value("--state-directory") != nil, !FileManager.default.fileExists(atPath: path)
        else {
            ApplicationLifecycle.afterCurrentEvent { NSApplication.shared.terminate(nil) }
            return
        }
        var result: [String: Any] = [
            "success": false, "guiObserved": false, "physicalOutputAccepted": false, "applicationBuildReady": false,
        ]
        func stage(_ name: String) {
            result["stage"] = name
            try? JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys]).write(
                to: URL(filePath: path + ".progress.json"), options: .atomic)
        }
        do {
            stage("library")
            if mode == "missing-runtime" {
                try require(!watch.runtimeAvailable && watch.errorKey == "playbackFailed" && watch.player == nil)
                try require(!watch.libraryPresentation(library.presentation).enabledActions.contains("startWatching"))
                await watch.close()
                result["missingRuntimeRejected"] = true
                result["success"] = true
                result.removeValue(forKey: "stage")
                finish(result, library: library, path: path)
                return
            }
            try require(watch.runtimeAvailable && watch.player == nil && !watch.playerPresented)
            await library.settled()
            result["libraryRestoreError"] = library.errorKey ?? ""
            let savedSelection = preferences.state.selectedMediaID
            result["savedSelectionPresent"] = savedSelection != nil
            if library.presentation.entries.isEmpty {
                try require(savedSelection == nil)
                library.choose(URL(filePath: file).deletingLastPathComponent())
                await library.settled()
            }
            let entry = library.presentation.entries.first { $0.title == URL(filePath: file).lastPathComponent }
            guard let entry else { throw Failure.condition }
            library.select(entry.id)
            guard let selection = library.selectedMedia() else { throw Failure.condition }
            try require(savedSelection == nil || savedSelection == entry.id)
            let expectedResume = preferences.state.resumePosition(for: entry.id)
            result["restoredPositionMs"] = expectedResume
            if mode != "normal" {
                stage(mode)
                watch.start(selection)
                if mode == "load-failure" {
                    try await until { watch.phase == .ended && watch.player == nil }
                    try require(watch.errorKey == "playbackFailed" && !watch.playerPresented)
                    result["failedLoadReleased"] = true
                } else if mode == "close-preparing" {
                    try await until { watch.player != nil }
                    try require(watch.phase == .preparing)
                    await watch.close()
                    await watch.close()
                    try require(watch.player == nil && !watch.playerPresented)
                    result["closeDuringPreparation"] = true
                } else if mode == "shared-session" {
                    try await until { watch.player?.view?.window != nil && watch.phase == .active }
                    guard let current = watch.player, let configuration = value("--shared-check-config") else {
                        throw Failure.condition
                    }
                    try await SharedPlaybackAcceptance.run(
                        controller: current, file: URL(filePath: file),
                        configuration: URL(filePath: configuration))
                    result["nativeSharedSession"] = true
                    result["helperConnectionAccepted"] = true
                } else if mode == "helper-correction" {
                    try await until { watch.player?.view?.window != nil && watch.phase == .active }
                    guard let current = watch.player else { throw Failure.condition }
                    try await HelperPlaybackAcceptance.run(player: current.player, scope: current.scope)
                    result["nativeHelperCorrections"] = true
                    result["helperConnectionAccepted"] = false
                } else if mode == "cancel-correction" {
                    try await until { watch.player?.view?.window != nil && watch.phase == .active }
                    guard let current = watch.player else { throw Failure.condition }
                    try await until {
                        let value = try await current.player.observe(current.scope)
                        return value.status == .ready && value.seekable && value.paused
                    }
                    try await current.player.seek(to: 1300, scope: current.scope)
                    try await until { abs(watch.positionMs - 1300) < 200 }
                    for command in ["seek", "rate", "pause"] {
                        let operation = Task {
                            withUnsafeCurrentTask { $0?.cancel() }
                            if command == "seek" {
                                try await current.player.seek(to: 0, scope: current.scope)
                            } else if command == "rate" {
                                try await current.player.setRate(1.25, scope: current.scope)
                            } else {
                                try await current.player.setPaused(false, scope: current.scope)
                            }
                        }
                        var cancelled = false
                        do { try await operation.value } catch is CancellationError { cancelled = true }
                        result["cancelled-\(command)"] = cancelled
                        let value = try await current.player.observe(current.scope)
                        result["actualPositionMs"] = value.positionMs
                        result["actualRate"] = value.rate
                        result["actualPaused"] = value.paused
                        try require(cancelled && value.paused && value.rate == 1 && abs(value.positionMs - 1300) < 200)
                    }
                    result["cancelledCorrectionsPreserveNativeState"] = true
                } else {
                    throw Failure.condition
                }
                await watch.close()
                result["success"] = true
                result.removeValue(forKey: "stage")
                finish(result, library: library, path: path)
                return
            }
            stage("start")
            watch.start(selection)
            try await until { watch.player?.view?.window != nil && watch.phase == .active }
            guard let player = watch.player, let view = player.view else { throw Failure.condition }
            let scope = player.scope
            try await until {
                let value = try await player.player.observe(scope)
                return value.status == .ready && value.paused && value.seekable
                    && abs(value.positionMs - expectedResume) < 300
            }
            watch.start(selection)
            try require(watch.player === player && watch.scope == scope)
            player.action("playPause", value: nil)
            try await until { try await player.player.observe(scope).positionMs >= max(500, expectedResume + 200) }
            stage("home-continue")
            player.action("showLibrary", value: nil)
            try require(!watch.playerPresented && watch.player === player)
            let hidden = try await player.player.observe(scope).positionMs
            try await until { try await player.player.observe(scope).positionMs >= hidden + 250 }
            watch.continueWatching()
            try require(
                watch.playerPresented && watch.player === player && player.view === view && watch.scope == scope)
            player.action("playPause", value: nil)
            try await until { try await player.player.observe(scope).paused }
            player.action("seek", value: 1300)
            try await until { abs(watch.positionMs - 1300) < 200 }
            stage("end")
            watch.end()
            try await until { watch.player == nil && !preferences.savingWatchState }
            stage("released")
            var released = false
            do { _ = try await player.player.observe(scope) } catch { released = true }
            try require(released && watch.scope != scope && !watch.playerPresented)
            watch.start(selection)
            stage("restart")
            try await until { watch.player?.view?.window != nil && watch.phase == .active }
            guard let resumed = watch.player else { throw Failure.condition }
            try require(resumed !== player && resumed.scope != scope)
            try await until {
                let value = try await resumed.player.observe(resumed.scope)
                return value.paused && abs(value.positionMs - 1300) < 250 && abs(watch.positionMs - 1300) < 250
            }
            watch.end()
            try await until { watch.player == nil && !preferences.savingWatchState }
            stage("cancel-close")
            watch.start(selection)
            watch.end()
            await watch.close()
            await watch.close()
            try require(watch.player == nil && !watch.playerPresented)
            try require(abs(preferences.state.resumePosition(for: entry.id) - 1300) < 250)
            result["sameOwnerHomeContinue"] = true
            result["nativeClockWhileHidden"] = true
            result["endReleasesNative"] = true
            result["resumeAfterNewOwner"] = true
            result["cancelBeforeAllocation"] = true
            result["idempotentClose"] = true
            result["success"] = true
            result.removeValue(forKey: "stage")
        } catch {
            result["failure"] = String(describing: error)
            await watch.close()
        }
        finish(result, library: library, path: path)
    }
    private static func finish(_ result: [String: Any], library: LibraryController, path: String) {
        library.close()
        do {
            try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys]).write(
                to: URL(filePath: path), options: .atomic)
        } catch { FileHandle.standardError.write(Data("Watch integration report failed\n".utf8)) }
        // Leave this MainActor job before AppKit enters its deferred-termination run loop.
        ApplicationLifecycle.afterCurrentEvent { NSApplication.shared.terminate(nil) }
    }
}
