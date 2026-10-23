import AppKit
import Foundation
import SyncWatchDomain

/// Activated only by the explicit local native acceptance entry point.
@MainActor enum PlaybackAcceptance {
    private enum Failure: Error { case timeout, surface, clock, pixels }
    private static func wait(
        _ controller: PlaybackController, until predicate: (PlaybackObservation) -> Bool
    ) async throws -> PlaybackObservation {
        let deadline = ContinuousClock.now.advanced(by: .seconds(15))
        while ContinuousClock.now < deadline {
            let value = try await controller.player.observe(controller.scope)
            if value.status == .failed { throw Failure.surface }
            if predicate(value) { return value }
            try await Task.sleep(for: .milliseconds(40))
        }
        throw Failure.timeout
    }
    static func run(controller: PlaybackController, report: URL) async {
        var result: [String: Any] = ["success": false, "physicalOutputAccepted": false]
        do {
            let initial = try await wait(controller) { $0.status == .ready && $0.paused && $0.seekable }
            guard initial.positionMs < 300, initial.durationMs == 4000 else { throw Failure.clock }
            controller.action("playPause", value: nil)
            _ = try await wait(controller) {
                !$0.paused && $0.positionMs >= 500 && $0.videoOutputs > 0 && $0.width == 320 && $0.height == 180
            }
            guard let window = controller.window, let view = controller.view, window.isVisible,
                !view.subviews.isEmpty
            else { throw Failure.surface }
            controller.action("playPause", value: nil)
            let paused = try await wait(controller) { $0.paused }
            try await Task.sleep(for: .milliseconds(300))
            let stable = try await controller.player.observe(controller.scope)
            guard stable.paused, abs(stable.positionMs - paused.positionMs) <= 60 else { throw Failure.clock }
            controller.action("seek", value: 2500)
            _ = try await wait(controller) { $0.paused && (2300...2700).contains($0.positionMs) }
            try await Task.sleep(for: .milliseconds(300))
            let forward = try await capture(
                window: window, view: view,
                output: report.deletingLastPathComponent().appendingPathComponent("forward.png"))
            controller.action("seek", value: 250)
            _ = try await wait(controller) { $0.paused && $0.positionMs < 650 }
            try await Task.sleep(for: .milliseconds(300))
            let backward = try await capture(
                window: window, view: view,
                output: report.deletingLastPathComponent().appendingPathComponent("backward.png"))
            if let forward, let backward {
                guard forward > 110, backward < 100, forward - backward > 50 else { throw Failure.pixels }
                result["presentedSeekPixelsAccepted"] = true
                result["forwardPixel"] = forward
                result["backwardPixel"] = backward
            } else {
                result["presentedSeekPixelsAccepted"] = false
                result["captureUnavailable"] = true
            }
            let original = window.frame
            window.setContentSize(
                NSSize(
                    width: view.bounds.width + view.bounds.width / 4,
                    height: view.bounds.height + view.bounds.height / 4))
            try await Task.sleep(for: .milliseconds(200))
            window.setFrame(original, display: true)
            let final = try await controller.player.observe(controller.scope)
            guard final.videoOutputs > 0, controller.view === view else { throw Failure.surface }
            for entering in [true, false] {
                controller.action("toggleFullscreen", value: nil)
                let deadline = ContinuousClock.now.advanced(by: .seconds(10))
                while window.styleMask.contains(.fullScreen) != entering, ContinuousClock.now < deadline {
                    try await Task.sleep(for: .milliseconds(50))
                }
                guard window.styleMask.contains(.fullScreen) == entering else { throw Failure.surface }
                try await Task.sleep(for: .milliseconds(500))
            }
            guard controller.view === view, try await controller.player.observe(controller.scope).videoOutputs > 0
            else { throw Failure.surface }
            result["nativeViewClass"] = NSStringFromClass(type(of: view.subviews[0]))
            result["actualNativeSurface"] = true
            result["resizeRetainedDrawable"] = true
            result["fullscreenRetainedDrawable"] = true
            result["actualPausedClock"] = true
            await controller.close()
            do {
                _ = try await controller.player.observe(controller.scope)
                throw Failure.surface
            } catch is Failure { throw Failure.surface } catch {}
            result["nativeReleasedBeforeView"] = true
            result["success"] = true
        } catch {
            result["failure"] = String(describing: error)
            await controller.close()
        }
        finish(report, result)
    }
    static func fail(controller: PlaybackController, report: URL, error: any Error) async {
        // Startup failure must not await the polling task from inside itself.
        await controller.player.close()
        finish(
            report,
            [
                "success": false, "failure": "startup", "diagnostic": String(describing: error),
                "physicalOutputAccepted": false,
            ])
    }
    private static func capture(window: NSWindow, view: NSView, output: URL) async throws -> Double? {
        let number = String(window.windowNumber)
        let frame = window.frame
        let point = window.convertToScreen(view.convert(view.bounds, to: nil)).origin
        let center = NSPoint(x: point.x + view.bounds.width / 2, y: point.y + view.bounds.height / 2)
        let path = output.path
        let status = try await Task.detached {
            let process = Process()
            process.executableURL = URL(filePath: "/usr/sbin/screencapture")
            process.arguments = ["-x", "-o", "-l", number, path]
            process.standardInput = FileHandle.nullDevice
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
            try process.run()
            process.waitUntilExit()
            return process.terminationStatus
        }.value
        guard status == 0, let image = NSBitmapImageRep(data: try Data(contentsOf: output)) else { return nil }
        let scale = Double(image.pixelsWide) / frame.width
        let x = Int((center.x - frame.minX) * scale)
        let y = Int((frame.maxY - center.y) * scale)
        guard (0..<image.pixelsWide).contains(x), (0..<image.pixelsHigh).contains(y),
            let color = image.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB)
        else { throw Failure.pixels }
        return Double(color.redComponent + color.greenComponent + color.blueComponent) / 3 * 255
    }
    private static func finish(_ report: URL, _ value: [String: Any]) {
        do {
            try JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]).write(
                to: report, options: .atomic)
        } catch { FileHandle.standardError.write(Data("Native playback report failed\n".utf8)) }
        NSApplication.shared.terminate(nil)
    }
}
