import Foundation
import SyncWatchBridge
import SyncWatchDomain

public struct SyncEndpoint: Sendable {
    let host: String
    let port: Int
    let room: String
    let username: String
    public init(host: String, port: Int, room: String, username: String) throws {
        guard !host.isEmpty, host.utf8.count <= 253,
            host.utf8.allSatisfy({
                (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0)
                    || [46, 58, 95, 45].contains($0)
            }), (1...65535).contains(port)
        else { throw SessionFailure.malformed }
        _ = try WireValue.string(room).text(256)
        _ = try WireValue.string(username).text(64)
        self.host = host
        self.port = port
        self.room = room
        self.username = username
    }
}

public enum LocalPlaybackAction: Sendable {
    case pause(Bool)
    case seek(Int64)
}

/// Application lifecycle and native observations only. Syncplay retains all synchronization decisions.
public actor PlaybackSession {
    private let player: any PlaybackPort
    private let scope: PlaybackScope
    private let helper: HelperProcess
    private let duration: Int64
    private var actions: [LocalPlaybackAction] = []
    private var frames: [Data] = []
    private var pending: [String: (kind: String, deadline: ContinuousClock.Instant)] = [:]
    private var completed: [String: (input: Data, result: Data)] = [:]
    private var completionOrder: [String] = []
    private var commandSequence: UInt64 = 0
    private var userSequence: UInt64 = 0
    private var correctionSequence: UInt64 = 0
    private var eventSequence: UInt64 = 0
    private var lastPing = ContinuousClock.now
    private let connectionDeadline = ContinuousClock.now.advanced(by: .seconds(15))
    private var connectedOnce = false
    private var readyRequested = false
    private var closing = false
    private var failure: (any Error)?
    private var reader: Task<Void, Never>?
    private var active: Task<PlaybackObservation, any Error>?
    private var shutdown: Task<Void, Never>?
    public private(set) var connected = false
    public private(set) var ready = false

    private init(player: any PlaybackPort, scope: PlaybackScope, helper: HelperProcess, duration: Int64) {
        self.player = player
        self.scope = scope
        self.helper = helper
        self.duration = duration
    }

    /// The caller supplies an authorized paused selection and integrity-checked development helper.
    public static func start(
        player: any PlaybackPort, scope: PlaybackScope, executable: URL, runtime: URL,
        helperRevision: String, mediaName: String, fileSize: UInt64, endpoint: SyncEndpoint
    ) async throws -> PlaybackSession {
        _ = try WireValue.string(mediaName).text(256)
        guard !mediaName.contains("/"), !mediaName.contains("\\"), fileSize <= PlaybackScope.maximumGeneration else {
            throw SessionFailure.malformed
        }
        let actual = try await player.observe(scope)
        try scope.check(clientRunID: actual.scope.clientRunID, mediaGeneration: actual.scope.mediaGeneration)
        guard actual.status == .ready, actual.paused, let duration = actual.durationMs, duration > 0 else {
            throw SessionFailure.unavailable
        }
        let helper = try await HelperProcess.launch(executable: executable, runtime: runtime)
        let session = PlaybackSession(player: player, scope: scope, helper: helper, duration: duration)
        do {
            try await session.bootstrap(
                revision: helperRevision, mediaName: mediaName, fileSize: fileSize, endpoint: endpoint)
            return session
        } catch {
            await session.close()
            throw error
        }
    }

    private func bootstrap(revision: String, mediaName: String, fileSize: UInt64, endpoint: SyncEndpoint) async throws {
        let hello = try await command("bridge.hello", ["supportedVersions": .array([.number(1)])])
        let reply = try await awaitReply(hello)
        guard reply.kind == "bridge.ready", try reply.payload["syncplayRevision"]!.text(40) == revision else {
            throw SessionFailure.malformed
        }
        let loaded = try await command(
            "player.loaded",
            [
                "mediaHandle": .string("selected-media"), "name": .string(mediaName),
                "durationMs": .number(Double(duration)), "fileSizeBytes": .number(Double(fileSize)),
            ])
        _ = try await awaitReply(loaded)
        let connect = try await command(
            "sync.connect",
            [
                "host": .string(endpoint.host), "port": .number(Double(endpoint.port)),
                "room": .string(endpoint.room), "username": .string(endpoint.username), "tls": .flag(true),
            ])
        _ = try await awaitReply(connect)
        reader = Task { [helper, weak self] in
            do {
                while !Task.isCancelled {
                    let data = try await helper.read()
                    guard let self else { break }
                    try await self.enqueue(data)
                }
            } catch { await self?.readFailed(error) }
        }
    }
    private func enqueue(_ frame: Data) throws {
        guard !closing else { return }
        guard frames.count < 64 else { throw SessionFailure.queueFull }
        frames.append(frame)
    }
    private func readFailed(_ error: any Error) { if !closing { failure = error } }

    @discardableResult public func request(_ action: LocalPlaybackAction) -> Bool {
        guard !closing, connected, actions.count < 32 else { return false }
        if case .seek(let position) = action, !(0...duration).contains(position) { return false }
        actions.append(action)
        return true
    }
    public func step() async throws -> PlaybackObservation {
        guard !closing, active == nil else { throw SessionFailure.concurrentOwner }
        let task = Task { try await pump() }
        active = task
        defer { active = nil }
        return try await withTaskCancellationHandler {
            try await task.value
        } onCancel: {
            task.cancel()
        }
    }
    private func checkOpen() throws {
        try Task.checkCancellation()
        guard !closing else { throw SessionFailure.unavailable }
        if let failure { throw failure }
    }
    private func pump() async throws -> PlaybackObservation {
        do {
            try checkOpen()
            let work = actions
            actions.removeAll(keepingCapacity: true)
            for action in work {
                try checkOpen()
                guard connected else { throw SessionFailure.unavailable }
                let kind: String
                let value: Double
                switch action {
                case .pause(let b):
                    kind = "player.setPaused"
                    value = b ? 1 : 0
                case .seek(let n):
                    kind = "player.setPosition"
                    value = Double(n)
                }
                let actual = try await apply(kind, value: value)
                guard userSequence < PlaybackScope.maximumGeneration else { throw SessionFailure.order }
                userSequence += 1
                try await publish(actual, user: userSequence)
            }
            let received = frames
            frames.removeAll(keepingCapacity: true)
            for data in received {
                try checkOpen()
                try await receive(HelperWire.decode(data, scope: scope))
            }
            guard !pending.values.contains(where: { ContinuousClock.now > $0.deadline }) else {
                throw SessionFailure.timeout
            }
            guard connectedOnce || ContinuousClock.now < connectionDeadline else { throw SessionFailure.timeout }
            if lastPing.duration(to: .now) >= .seconds(2) {
                _ = try await command("bridge.ping", [:])
                lastPing = .now
            }
            let actual = try await observe()
            try await publish(actual)
            if connected && !readyRequested {
                _ = try await command("sync.setReady", ["ready": .flag(true)])
                readyRequested = true
            }
            return actual
        } catch {
            connected = false
            ready = false
            failure = error
            try? await player.stop(scope)
            await helper.close()
            throw error
        }
    }
    private func observe() async throws -> PlaybackObservation {
        let actual = try await player.observe(scope)
        try checkOpen()
        try scope.check(clientRunID: actual.scope.clientRunID, mediaGeneration: actual.scope.mediaGeneration)
        guard actual.status == .ready, actual.durationMs == duration, !actual.ended else {
            throw SessionFailure.unavailable
        }
        return actual
    }
    private func apply(_ kind: String, value: Double) async throws -> PlaybackObservation {
        try checkOpen()
        switch kind {
        case "player.setPaused": try await player.setPaused(value != 0, scope: scope)
        case "player.setPosition":
            guard value <= Double(duration) else { throw SessionFailure.malformed }
            try await player.seek(to: Int64(value), scope: scope)
        case "player.setSpeed": try await player.setRate(value, scope: scope)
        default: break
        }
        let started = ContinuousClock.now
        while true {
            let actual = try await observe()
            let applied: Bool
            switch kind {
            case "player.setPaused": applied = actual.paused == (value != 0)
            case "player.setPosition": applied = abs(Double(actual.positionMs) - value) <= 1000
            case "player.setSpeed": applied = abs(actual.rate - value) < 0.01
            default: applied = true
            }
            if applied { return actual }
            guard started.duration(to: .now) < .seconds(2) else { throw SessionFailure.timeout }
            try await Task.sleep(for: .milliseconds(20))
        }
    }
    private func publish(_ actual: PlaybackObservation, user: UInt64? = nil) async throws {
        try await helper.send(
            HelperWire.encode(
                scope, kind: "player.state",
                payload: [
                    "status": .string("ready"),
                    "positionMs": .number(Double(actual.positionMs)), "durationMs": .number(Double(duration)),
                    "paused": .flag(actual.paused),
                    "rate": .number(actual.rate), "seekable": .flag(actual.seekable),
                ], user: user))
    }
    private func command(_ kind: String, _ payload: [String: WireValue]) async throws -> String {
        guard pending.count < 16, commandSequence < PlaybackScope.maximumGeneration else {
            throw SessionFailure.queueFull
        }
        commandSequence += 1
        let id = "cmd-\(commandSequence)"
        pending[id] = (kind, .now.advanced(by: .seconds(5)))
        try await helper.send(HelperWire.encode(scope, kind: kind, payload: payload, id: id))
        return id
    }
    private func awaitReply(_ id: String) async throws -> HelperFrame {
        while true {
            guard let request = pending[id], ContinuousClock.now < request.deadline else {
                throw SessionFailure.timeout
            }
            // Cancelling the deadline loser kills/releases a blocked inherited-pipe read.
            let data = try await withThrowingTaskGroup(of: Data.self) { group in
                group.addTask { try await self.helper.read() }
                group.addTask {
                    try await Task.sleep(for: .seconds(5))
                    throw SessionFailure.timeout
                }
                defer { group.cancelAll() }
                return try await group.next()!
            }
            let frame = try HelperWire.decode(data, scope: scope)
            try await receive(frame)
            if frame.reply && frame.id == id { return frame }
        }
    }
    private func receive(_ frame: HelperFrame) async throws {
        if frame.reply {
            guard let request = pending.removeValue(forKey: frame.id),
                frame.kind == (request.kind == "bridge.hello" ? "bridge.ready" : "bridge.result")
            else { throw SessionFailure.order }
            return
        }
        if let after = frame.afterUserAction {
            if let replay = completed[frame.id] {
                guard replay.input == frame.bytes else { throw SessionFailure.order }
                try await helper.send(replay.result)
                return
            }
            let number = UInt64(frame.id.dropFirst(4))!
            guard number > correctionSequence, after <= userSequence else { throw SessionFailure.order }
            correctionSequence = number
            let result: Data
            if after < userSequence {
                result = try HelperWire.encode(
                    scope, kind: "bridge.error",
                    payload: [
                        "code": .string("cancelled"), "message": .string("cancelled"), "retryable": .flag(false),
                    ], replyTo: frame.id)
            } else {
                let value: Double
                switch frame.kind {
                case "player.setPaused": value = try frame.payload["paused"]!.flag() ? 1 : 0
                case "player.setPosition": value = Double(try frame.payload["positionMs"]!.position())
                case "player.setSpeed":
                    guard case .number(let n) = frame.payload["rate"] else { throw SessionFailure.malformed }
                    value = n
                default:
                    guard try frame.payload["mediaHandle"]!.text() == "selected-media" else {
                        throw SessionFailure.unavailable
                    }
                    value = 0
                }
                let actual = try await apply(frame.kind, value: value)
                result = try HelperWire.encode(
                    scope, kind: "player.result",
                    payload: [
                        "status": .string("applied"), "positionMs": .number(Double(actual.positionMs)),
                        "paused": .flag(actual.paused),
                    ], replyTo: frame.id)
            }
            completed[frame.id] = (frame.bytes, result)
            completionOrder.append(frame.id)
            if completionOrder.count > 64 { completed.removeValue(forKey: completionOrder.removeFirst()) }
            try await helper.send(result)
            return
        }
        let number = UInt64(frame.id.dropFirst(6))!
        guard number > eventSequence else { throw SessionFailure.order }
        eventSequence = number
        if frame.kind == "sync.connection" {
            connected = try frame.payload["state"]!.text() == "connected"
            guard connected || !connectedOnce else { throw SessionFailure.unavailable }
            connectedOnce = connectedOnce || connected
        } else if frame.kind == "sync.readiness" {
            ready = try frame.payload["ready"]!.flag()
        }
    }
    public func close() async {
        if let shutdown {
            await shutdown.value
            return
        }
        closing = true
        connected = false
        ready = false
        actions.removeAll()
        frames.removeAll()
        let work = active
        let read = reader
        let task = Task { [player, helper, scope] in
            work?.cancel()
            _ = await work?.result
            try? await player.stop(scope)
            await helper.close()
            read?.cancel()
            await read?.value
        }
        shutdown = task
        await task.value
    }
}
