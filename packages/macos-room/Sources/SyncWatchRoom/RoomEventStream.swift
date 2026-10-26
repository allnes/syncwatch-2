import Foundation

/// Bounded, single-consumer event stream. The room owner must decode each message before applying it.
public actor RoomEventStream {
    private let socket: URLSessionWebSocketTask
    private var pump: Task<Void, Never>?
    private var queue: [Data] = []
    private var waiter: CheckedContinuation<Data, Error>?
    private var failure: RoomProtocolFailure?
    init(socket: URLSessionWebSocketTask) { self.socket = socket }
    func start() {
        guard pump == nil, failure == nil else { return }
        socket.maximumMessageSize = RoomWire.maximumBytes
        socket.resume()
        pump = Task { await read() }
    }
    public func receive() async throws -> Data {
        try Task.checkCancellation()
        if !queue.isEmpty { return queue.removeFirst() }
        if let failure { throw failure }
        guard waiter == nil else { throw RoomProtocolFailure.malformed }
        return try await withTaskCancellationHandler(
            operation: {
                try await withCheckedThrowingContinuation { waiter = $0 }
            }, onCancel: { Task { await self.close() } })
    }
    public func close() async {
        finish(.closed)
        pump?.cancel()
        if let pump { await pump.value }
    }
    func transportEnded() async {
        finish(.transport)
        pump?.cancel()
        if let pump { await pump.value }
    }
    private func read() async {
        do {
            while !Task.isCancelled {
                let message = try await receiveMessage()
                guard case .string(let text) = message else { throw RoomProtocolFailure.malformed }
                let bytes = Data(text.utf8)
                _ = try RoomWire.object(bytes)
                guard failure == nil else { return }
                if let pending = waiter {
                    waiter = nil
                    pending.resume(returning: bytes)
                } else {
                    guard queue.count < 32 else { throw RoomProtocolFailure.rejected("queueFull") }
                    queue.append(bytes)
                }
            }
            finish(.closed)
        } catch let error as RoomProtocolFailure { finish(error) } catch { finish(.transport) }
    }
    private func receiveMessage() async throws -> URLSessionWebSocketTask.Message {
        let pending = RoomSocketRead()
        let socket = socket
        return try await withTaskCancellationHandler(
            operation: {
                try await withCheckedThrowingContinuation { continuation in
                    if pending.install(continuation) {
                        socket.receive { pending.complete($0) }
                    }
                }
            },
            onCancel: {
                // Foundation can retain an idle async receive after socket cancellation.
                // Own the continuation so joining the reader never depends on that callback.
                pending.complete(.failure(CancellationError()))
                socket.cancel()
            })
    }
    private func finish(_ error: RoomProtocolFailure) {
        guard failure == nil else { return }
        failure = error
        queue.removeAll()
        // Teardown must cancel the pending SDK receive rather than wait for a peer close handshake.
        socket.cancel()
        let pending = waiter
        waiter = nil
        pending?.resume(throwing: error)
    }
}

/// Completion and cancellation may race, including cancellation before registration.
private final class RoomSocketRead: @unchecked Sendable {
    private let lock = NSLock()
    private var result: Result<URLSessionWebSocketTask.Message, Error>?
    private var continuation: CheckedContinuation<URLSessionWebSocketTask.Message, Error>?
    func install(_ continuation: CheckedContinuation<URLSessionWebSocketTask.Message, Error>) -> Bool {
        lock.lock()
        if let result {
            lock.unlock()
            continuation.resume(with: result)
            return false
        }
        self.continuation = continuation
        lock.unlock()
        return true
    }
    func complete(_ result: Result<URLSessionWebSocketTask.Message, Error>) {
        lock.lock()
        guard self.result == nil else {
            lock.unlock()
            return
        }
        self.result = result
        let pending = continuation
        continuation = nil
        lock.unlock()
        pending?.resume(with: result)
    }
}

/// URLSession can finish a socket without completing an idle receive callback.
/// A weak binding avoids retaining the client through its SDK delegate.
final class RoomSocketTermination: @unchecked Sendable {
    private let lock = NSLock()
    private var ended = false
    private weak var stream: RoomEventStream?
    func bind(_ stream: RoomEventStream) {
        lock.lock()
        self.stream = stream
        let ended = ended
        lock.unlock()
        if ended { Task { await stream.transportEnded() } }
    }
    func finish() {
        lock.lock()
        guard !ended else {
            lock.unlock()
            return
        }
        ended = true
        let stream = stream
        lock.unlock()
        if let stream { Task { await stream.transportEnded() } }
    }
}
