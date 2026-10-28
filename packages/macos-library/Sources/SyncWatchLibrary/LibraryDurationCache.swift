import Foundation

/// Bounded, process-local observations, keyed by the complete scanned file version.
/// Durations are display hints only; selected-file inspection and shared admission stay fresh.
public struct LibraryDurationCache: Sendable {
    private struct Entry: Sendable {
        let file: LocalMediaFile
        let duration: Int64
    }
    private let capacity: Int
    private var entries: [String: Entry] = [:]
    private var order: [String] = []
    public init(capacity: Int = 256) {
        precondition(capacity > 0)
        self.capacity = capacity
    }
    public func duration(for file: LocalMediaFile) -> Int64? {
        guard let entry = entries[file.id], entry.file == file else { return nil }
        return entry.duration
    }
    public mutating func record(_ duration: Int64?, for file: LocalMediaFile) {
        entries.removeValue(forKey: file.id)
        order.removeAll { $0 == file.id }
        guard let duration, duration > 0 else { return }
        entries[file.id] = Entry(file: file, duration: duration)
        order.append(file.id)
        while order.count > capacity { entries.removeValue(forKey: order.removeFirst()) }
    }
    public mutating func reconcile(_ files: [LocalMediaFile]) {
        let current = Dictionary(uniqueKeysWithValues: files.map { ($0.id, $0) })
        entries = entries.filter { current[$0.key] == $0.value.file && $0.value.file.modificationDate != nil }
        order.removeAll { entries[$0] == nil }
    }
    public mutating func clear() {
        entries = [:]
        order = []
    }
}
