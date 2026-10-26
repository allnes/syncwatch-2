import Foundation
import SyncWatchBridge
import SyncWatchDomain

/// Explicit native boundary check; no helper/server connection is established.
enum HelperPlaybackAcceptance {
    static func run(player: any PlaybackPort, scope: PlaybackScope) async throws {
        let wire = try PlaybackScope(clientRunID: "helper-run", mediaGeneration: 7)
        func command(_ id: Int, _ kind: String, _ payload: [String: Any]) throws -> PlayerCorrection {
            var frame = try JSONSerialization.data(withJSONObject: [
                "v": 1, "id": "cmd-\(id)", "type": kind, "clientRunId": wire.clientRunID,
                "mediaGeneration": wire.mediaGeneration, "afterUserAction": 0, "payload": payload,
            ])
            frame.append(10)
            return try PlayerCorrection.decode(frame, wireScope: wire)
        }
        func until(_ predicate: @Sendable (PlaybackObservation) -> Bool) async throws {
            let deadline = ContinuousClock.now.advanced(by: .seconds(3))
            while ContinuousClock.now < deadline {
                if predicate(try await player.observe(scope)) { return }
                try await Task.sleep(for: .milliseconds(40))
            }
            throw PlayerCorrectionFailure.unavailable
        }
        try await until { $0.status == .ready && $0.paused && $0.seekable }
        let seek = try command(1, "player.setPosition", ["positionMs": 2000])
        let actual = try await seek.apply(to: player, nativeScope: scope, authorizedHandle: "media-1")
        let result = try JSONSerialization.jsonObject(with: seek.result(actual, nativeScope: scope)) as! [String: Any]
        guard result["clientRunId"] as? String == wire.clientRunID,
            (result["payload"] as? [String: Any])?["positionMs"] as? Int64 == actual.positionMs
        else { throw PlayerCorrectionFailure.malformed }
        try await until { abs($0.positionMs - 2000) < 200 }
        _ = try await command(2, "player.setPaused", ["paused": false]).apply(
            to: player, nativeScope: scope, authorizedHandle: "media-1")
        try await until { !$0.paused }
        _ = try await command(3, "player.setPaused", ["paused": true]).apply(
            to: player, nativeScope: scope, authorizedHandle: "media-1")
        try await until { $0.paused }
        _ = try await command(4, "player.setSpeed", ["rate": 1.25]).apply(
            to: player, nativeScope: scope, authorizedHandle: "media-1")
        try await until { abs($0.rate - 1.25) < 0.001 }
        let before = try await player.observe(scope)
        let kept = try await command(5, "player.openFile", ["mediaHandle": "media-1"]).apply(
            to: player, nativeScope: scope, authorizedHandle: "media-1")
        guard kept.paused, abs(kept.positionMs - before.positionMs) < 100 else {
            throw PlayerCorrectionFailure.unavailable
        }
        do {
            _ = try await command(6, "player.openFile", ["mediaHandle": "media-other"]).apply(
                to: player, nativeScope: scope, authorizedHandle: "media-1")
            throw PlayerCorrectionFailure.malformed
        } catch PlayerCorrectionFailure.unauthorizedHandle {}
    }
}
