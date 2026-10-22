import Darwin
import Foundation

/// Owns one helper and serialized pipe I/O, independent of views and playback policy.
public final class HelperProcess: @unchecked Sendable {
    private let process: Process
    private let input: FileHandle
    private let output: FileHandle
    private let errors: FileHandle
    private let reader = DispatchQueue(label: "syncwatch.helper.read", qos: .utility)
    private let writer = DispatchQueue(label: "syncwatch.helper.write", qos: .utility)
    private let lock = NSLock()
    private var closed = false
    private var reading = false
    private var writing = false
    private var buffer = Data()
    private static let maximumFrameBytes = 65_536  // contracts/manifest.json, including LF

    public enum Failure: Error { case malformed, frameTooLarge, stopped, closed, queueFull }

    private init(executable: URL, runtime: URL) throws {
        guard executable.isFileURL, runtime.isFileURL,
            executable.path.hasPrefix("/"), runtime.path.hasPrefix("/")
        else { throw Failure.malformed }
        let process = Process()
        let stdin = Pipe()
        let stdout = Pipe()
        let stderr = Pipe()
        process.executableURL = executable
        process.arguments = [runtime.path]
        process.currentDirectoryURL = runtime
        process.environment = ProcessInfo.processInfo.environment.filter { !$0.key.uppercased().hasPrefix("PYTHON") }
        process.standardInput = stdin
        process.standardOutput = stdout
        process.standardError = stderr
        self.process = process
        input = stdin.fileHandleForWriting
        output = stdout.fileHandleForReading
        errors = stderr.fileHandleForReading
        errors.readabilityHandler = { handle in
            if handle.availableData.isEmpty { handle.readabilityHandler = nil }
        }
        try process.run()
    }

    public static func launch(executable: URL, runtime: URL) async throws -> HelperProcess {
        try await Task.detached { try HelperProcess(executable: executable, runtime: runtime) }.value
    }

    public var processID: Int32 { process.processIdentifier }

    private static func validate(_ frame: Data) throws {
        guard (2...maximumFrameBytes).contains(frame.count), frame.last == 10,
            !frame.dropLast().contains(10), !frame.contains(13), String(data: frame, encoding: .utf8) != nil
        else { throw Failure.malformed }
    }

    public func send(_ frame: Data) async throws {
        try Self.validate(frame)
        try begin(reading: false)
        defer { end(reading: false) }
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                writer.async {
                    do {
                        try self.checkOpen()
                        try self.input.write(contentsOf: frame)
                        continuation.resume()
                    } catch {
                        self.kill()
                        continuation.resume(throwing: error)
                    }
                }
            }
        } onCancel: {
            self.kill()
        }
    }

    public func read() async throws -> Data {
        try begin(reading: true)
        defer { end(reading: true) }
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                reader.async {
                    do {
                        try self.checkOpen()
                        while true {
                            if let newline = self.buffer.firstIndex(of: 10) {
                                let frame = self.buffer.prefix(through: newline)
                                self.buffer.removeSubrange(...newline)
                                let data = Data(frame)
                                try Self.validate(data)
                                continuation.resume(returning: data)
                                return
                            }
                            if self.buffer.count >= Self.maximumFrameBytes { throw Failure.frameTooLarge }
                            var bytes = [UInt8](
                                repeating: 0, count: min(4096, Self.maximumFrameBytes - self.buffer.count))
                            let count = Darwin.read(self.output.fileDescriptor, &bytes, bytes.count)
                            if count < 0 && errno == EINTR { continue }
                            guard count > 0 else { throw Failure.stopped }
                            self.buffer.append(contentsOf: bytes.prefix(count))
                        }
                    } catch {
                        self.kill()
                        continuation.resume(throwing: error)
                    }
                }
            }
        } onCancel: {
            self.kill()
        }
    }

    private func checkOpen() throws {
        lock.lock()
        defer { lock.unlock() }
        if closed { throw Failure.closed }
    }

    private func begin(reading: Bool) throws {
        lock.lock()
        defer { lock.unlock() }
        if closed { throw Failure.closed }
        if reading ? self.reading : writing { throw Failure.queueFull }
        if reading { self.reading = true } else { writing = true }
    }

    private func end(reading: Bool) {
        lock.lock()
        defer { lock.unlock() }
        if reading { self.reading = false } else { writing = false }
    }

    private func kill() {
        if process.isRunning { _ = Darwin.kill(process.processIdentifier, SIGKILL) }
    }

    public func close() async {
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + 3) { self.kill() }
        await withCheckedContinuation { continuation in
            writer.async {
                self.lock.lock()
                let wasClosed = self.closed
                self.closed = true
                self.lock.unlock()
                if !wasClosed {
                    try? self.input.close()
                    self.process.waitUntilExit()
                    self.errors.readabilityHandler = nil
                    try? self.output.close()
                    try? self.errors.close()
                }
                continuation.resume()
            }
        }
    }

    deinit { kill() }
}
