import CoreServices
import Darwin
import Foundation

public enum LibraryMonitorEvent: Sendable { case changed, unavailable }

/// Invalidations only: callers reconcile with a completed scan, never apply event paths as catalog facts.
public final class LibraryChangeMonitor: Sendable {
    public let changes: AsyncStream<LibraryMonitorEvent>
    private let source: LibraryEventSource

    public init(root: URL, recursive: Bool) throws {
        let pair = AsyncStream<LibraryMonitorEvent>.makeStream(bufferingPolicy: .bufferingNewest(1))
        changes = pair.stream
        source = try LibraryEventSource(root: root, recursive: recursive, sink: pair.continuation)
        pair.continuation.onTermination = { [weak source] _ in source?.close() }
        try source.start()
    }

    public var isActive: Bool { source.isActive }
    public func close() { source.close() }
    deinit { source.close() }
}

/// FSEvents and its context are confined to this serial queue. close drains that same queue.
private final class LibraryEventSource: @unchecked Sendable {
    private let queue = DispatchQueue(label: "SyncWatch.LibraryChanges")
    private let queueKey = DispatchSpecificKey<Bool>()
    private let root: String
    private let recursive: Bool
    private let sink: AsyncStream<LibraryMonitorEvent>.Continuation
    private var stream: FSEventStreamRef?
    private var stopped = false

    init(root: URL, recursive: Bool, sink: AsyncStream<LibraryMonitorEvent>.Continuation) throws {
        guard root.isFileURL, root.path.hasPrefix("/"), !root.path.utf8.contains(0),
            let canonical = realpath(root.path, nil)
        else { throw CocoaError(.fileReadNoSuchFile) }
        defer { free(canonical) }
        // FSEvents reports physical paths. Foundation can retain the /var alias
        // even after resolvingSymlinksInPath, while events arrive under /private/var.
        self.root = String(cString: canonical)
        self.recursive = recursive
        self.sink = sink
        queue.setSpecific(key: queueKey, value: true)
    }
    private func serialized<T>(_ operation: () throws -> T) rethrows -> T {
        if DispatchQueue.getSpecific(key: queueKey) == true { return try operation() }
        return try queue.sync(execute: operation)
    }
    var isActive: Bool { serialized { !stopped && stream != nil } }
    func start() throws {
        try serialized {
            guard try URL(fileURLWithPath: root).resourceValues(forKeys: [.isDirectoryKey]).isDirectory == true else {
                throw CocoaError(.fileReadNoSuchFile)
            }
            var context = FSEventStreamContext(
                version: 0, info: Unmanaged.passUnretained(self).toOpaque(),
                retain: { value in
                    guard let value else { return nil }
                    _ = Unmanaged<LibraryEventSource>.fromOpaque(value).retain()
                    return value
                },
                release: { value in
                    if let value { Unmanaged<LibraryEventSource>.fromOpaque(value).release() }
                }, copyDescription: nil)
            let flags = FSEventStreamCreateFlags(kFSEventStreamCreateFlagFileEvents | kFSEventStreamCreateFlagWatchRoot)
            guard
                let created = FSEventStreamCreate(
                    nil,
                    { _, info, count, paths, flags, _ in
                        guard let info else { return }
                        Unmanaged<LibraryEventSource>.fromOpaque(info).takeUnretainedValue()
                            .receive(count: count, paths: paths, flags: flags)
                    }, &context, [root] as CFArray, FSEventStreamEventId(kFSEventStreamEventIdSinceNow), 0.2, flags)
            else { throw CocoaError(.fileReadUnknown) }
            stream = created
            FSEventStreamSetDispatchQueue(created, queue)
            guard FSEventStreamStart(created) else {
                close()
                throw CocoaError(.fileReadUnknown)
            }
        }
    }
    private func receive(count: Int, paths: UnsafeMutableRawPointer, flags: UnsafePointer<FSEventStreamEventFlags>) {
        guard !stopped else { return }
        let names = paths.assumingMemoryBound(to: UnsafePointer<CChar>.self)
        for index in 0..<count {
            let event = flags[index]
            if event & FSEventStreamEventFlags(kFSEventStreamEventFlagRootChanged | kFSEventStreamEventFlagUnmount) != 0
            {
                sink.yield(.unavailable)
                sink.finish()
                close()
                return
            }
            // Dropped/coalesced events require full reconciliation, even for a flat listing.
            if event & FSEventStreamEventFlags(kFSEventStreamEventFlagMustScanSubDirs) != 0 {
                sink.yield(.changed)
                continue
            }
            let path = String(cString: names[index])
            guard path == root || path.hasPrefix(root + "/") else { continue }
            let relative = path == root ? "" : String(path.dropFirst(root.count + 1))
            if recursive || !relative.contains("/") { sink.yield(.changed) }
        }
    }
    func close() {
        serialized {
            guard !stopped else { return }
            stopped = true
            if let stream {
                FSEventStreamStop(stream)
                FSEventStreamInvalidate(stream)
                FSEventStreamRelease(stream)
                self.stream = nil
            }
            sink.finish()
        }
    }
}
