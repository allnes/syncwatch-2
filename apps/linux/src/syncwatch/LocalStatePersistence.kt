package syncwatch

import syncwatch.domain.LocalState
import syncwatch.domain.LocalStateRead
import syncwatch.domain.LocalStateStore

/** Serialize all access to the synchronous UI-independent domain port. */
internal class SerializedLocalStateStore(private val store: LocalStateStore) : LocalStateStore {
    private val gate = Any()
    override fun read(): LocalStateRead = synchronized(gate) { store.read() }
    override fun write(state: LocalState) = synchronized(gate) { store.write(state) }
}
