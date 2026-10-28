namespace SyncWatch.Library;

/// <summary>Bounded process-local display hints, never selected/shared input authorization.</summary>
public sealed class LibraryDurationCache
{
    private readonly int capacity;
    private readonly Dictionary<string, (LocalMediaFile File, long Duration)> entries = new();
    private readonly List<string> order = [];
    public LibraryDurationCache(int capacity = 256)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(capacity); this.capacity = capacity;
    }
    public long? Duration(LocalMediaFile file) => entries.TryGetValue(file.Id, out var entry) && entry.File == file ? entry.Duration : null;
    public void Record(long? duration, LocalMediaFile file)
    {
        entries.Remove(file.Id); order.Remove(file.Id);
        if (duration is not > 0) return;
        entries[file.Id] = (file, duration.Value); order.Add(file.Id);
        while (order.Count > capacity) { entries.Remove(order[0]); order.RemoveAt(0); }
    }
    public void Reconcile(IReadOnlyList<LocalMediaFile> files)
    {
        var current = files.ToDictionary(file => file.Id);
        foreach (string id in order.ToArray())
            if (!current.TryGetValue(id, out var file) || file != entries[id].File) { entries.Remove(id); order.Remove(id); }
    }
    public void Clear() { entries.Clear(); order.Clear(); }
}
