using System.Threading.Channels;

namespace SyncWatch.Library;

public enum LibraryMonitorEvent { Changed, Unavailable }

/// <summary>Invalidations only. Reconcile with a completed scan instead of trusting event paths.</summary>
public sealed class LibraryChangeMonitor : IDisposable
{
    private readonly object gate = new();
    private readonly FileSystemWatcher watcher;
    private readonly Channel<LibraryMonitorEvent> events = Channel.CreateBounded<LibraryMonitorEvent>(new BoundedChannelOptions(1)
    { FullMode = BoundedChannelFullMode.DropOldest, SingleReader = true, AllowSynchronousContinuations = false });
    private bool stopped;
    private bool failed;
    public bool IsActive { get { lock (gate) return !stopped && !failed; } }
    public IAsyncEnumerable<LibraryMonitorEvent> Changes(CancellationToken cancellation = default) => events.Reader.ReadAllAsync(cancellation);

    public LibraryChangeMonitor(string root, bool recursive)
    {
        if (!Path.IsPathFullyQualified(root) || !Directory.Exists(root)) throw new IOException("library-watch-root");
        watcher = new(root)
        {
            IncludeSubdirectories = recursive,
            NotifyFilter = NotifyFilters.FileName | NotifyFilters.DirectoryName | NotifyFilters.LastWrite | NotifyFilters.Size
        };
        watcher.Changed += Changed; watcher.Created += Changed; watcher.Deleted += Changed; watcher.Renamed += Changed;
        watcher.Error += (_, value) =>
        {
            lock (gate)
            {
                if (stopped || failed) return;
                // A lost buffer is an invalidation, not permission to apply a partial event history.
                failed = value.GetException() is not InternalBufferOverflowException;
                events.Writer.TryWrite(failed ? LibraryMonitorEvent.Unavailable : LibraryMonitorEvent.Changed);
                if (failed) events.Writer.TryComplete();
            }
        };
        try { watcher.EnableRaisingEvents = true; }
        catch { watcher.Dispose(); throw; }
    }
    private void Changed(object sender, FileSystemEventArgs value)
    {
        lock (gate) { if (!stopped && !failed) events.Writer.TryWrite(LibraryMonitorEvent.Changed); }
    }
    public void Dispose()
    {
        lock (gate)
        {
            if (stopped) return;
            stopped = true;
            events.Writer.TryComplete();
        }
        watcher.Dispose();
    }
}
