import Foundation
import SyncWatchDomain

/// All access to the synchronous port is serialized before crossing executors.
/// The wrapped domain port has no UI dependency; the lock protects every call.
final class SerializedLocalStateStore: LocalStateStore, @unchecked Sendable {
    private let base: any LocalStateStore
    private let lock = NSLock()
    init(_ base: any LocalStateStore) { self.base = base }
    func read() throws -> LocalStateRead { try lock.withLock { try base.read() } }
    func write(_ state: LocalState) throws { try lock.withLock { try base.write(state) } }
}
