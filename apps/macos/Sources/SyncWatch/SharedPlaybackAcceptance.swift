import Foundation
import SyncWatchBridge
import SyncWatchDomain

/// Explicit, authored-fixture application check. Control files dispatch the same
/// controller actions as PlayerChrome; exported state always comes from VLC.
@MainActor enum SharedPlaybackAcceptance {
    static func run(controller: PlaybackController, file: URL, configuration: URL) async throws {
        struct Configuration: Decodable {
            let runtime: String
            let executable: String
            let control: String
            let state: String
            let host: String
            let port: Int
            let room: String
            let username: String
        }
        let config = try JSONDecoder().decode(Configuration.self, from: Data(contentsOf: configuration))
        let runtime = URL(filePath: config.runtime)
        let executable = URL(filePath: config.executable)
        let control = URL(filePath: config.control)
        let output = URL(filePath: config.state)
        let endpoint = SyncplayEndpoint(
            host: config.host, port: config.port, room: config.room, username: config.username)
        let expires = ContinuousClock.now.advanced(by: .seconds(900))
        var observation: PlaybackObservation
        repeat {
            observation = try await controller.player.observe(controller.scope)
            guard ContinuousClock.now < expires else { throw HelperSessionFailure.timeout }
            if observation.status != .ready || !observation.seekable { try await Task.sleep(for: .milliseconds(40)) }
        } while observation.status != .ready || !observation.seekable
        guard let duration = observation.durationMs, duration > 0 else { throw HelperSessionFailure.unavailable }
        guard let size = try FileManager.default.attributesOfItem(atPath: file.path)[.size] as? NSNumber else {
            throw HelperSessionFailure.malformed
        }
        let revision = try String(
            contentsOf: runtime.appendingPathComponent("app/syncplay-revision.txt"), encoding: .ascii
        )
        .trimmingCharacters(in: .whitespacesAndNewlines)
        let transport = try await HelperProcess.launch(executable: executable, runtime: runtime)
        try await controller.connectShared(
            transport: transport, endpoint: endpoint,
            media: SharedMedia(
                handle: "fixture-media", name: file.lastPathComponent, durationMs: duration,
                fileSizeBytes: size.uint64Value), revision: revision)
        var sequence = 0
        while ContinuousClock.now < expires {
            if let shared = controller.sharedState {
                guard shared.connection != .failed else { throw HelperSessionFailure.unavailable }
                let actual = try await controller.player.observe(controller.scope)
                let value: [String: Any] = [
                    "connection": String(describing: shared.connection), "ready": shared.ready,
                    "acceptedUsername": shared.acceptedUsername ?? "",
                    "participants": shared.participants.map(\.username),
                    "positionMs": actual.positionMs, "paused": actual.paused, "rate": actual.rate,
                    "sequence": actual.sequence, "controlSequence": sequence, "guiObserved": false,
                    "physicalOutputAccepted": false,
                ]
                try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]).write(
                    to: output, options: .atomic)
            }
            if FileManager.default.fileExists(atPath: control.path) {
                guard
                    let instruction = try JSONSerialization.jsonObject(with: Data(contentsOf: control))
                        as? [String: Any],
                    let next = instruction["sequence"] as? Int, let action = instruction["action"] as? String
                else {
                    throw HelperSessionFailure.malformed
                }
                if next > sequence {
                    guard next == sequence + 1 else { throw HelperSessionFailure.malformed }
                    if action == "finish" { return }
                    guard ["playPause", "seek", "setMovieVolume", "muteMovie"].contains(action) else {
                        throw HelperSessionFailure.malformed
                    }
                    controller.action(action, value: (instruction["value"] as? NSNumber)?.doubleValue)
                    sequence = next
                }
            }
            try await Task.sleep(for: .milliseconds(100))
        }
        throw HelperSessionFailure.timeout
    }
}
