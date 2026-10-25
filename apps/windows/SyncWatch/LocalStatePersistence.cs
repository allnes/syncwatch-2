using SyncWatch.Domain;

namespace SyncWatch;

// The synchronous domain port has no UI dependency. One gate owns every read/write.
internal sealed class SerializedLocalStateStore(ILocalStateStore store) : ILocalStateStore
{
    private readonly object gate = new();
    public LocalStateRead Read() { lock (gate) return store.Read(); }
    public void Write(LocalState state) { lock (gate) store.Write(state); }
}
