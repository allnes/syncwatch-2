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
        guard pump == nil else { return }
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
    private func read() async {
        do {
            while !Task.isCancelled {
                let message = try await socket.receive()
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
    private func finish(_ error: RoomProtocolFailure) {
        guard failure == nil else { return }
        failure = error
        queue.removeAll()
        socket.cancel(with: .goingAway, reason: nil)
        let pending = waiter
        waiter = nil
        pending?.resume(throwing: error)
    }
}
