using System.Threading.Channels;

namespace SyncWatch.Library;

public enum LibraryMonitorEvent { Changed, Unavailable }

/// <summary>Invalidations only. Reconcile with a completed scan instead of trusting event paths.</summary>
public sealed class LibraryChangeMonitor : IDisposable
{
    private readonly object gate = new();
    private readonly FileSystemWatcher watcher;
    private readonly FileSystemWatcher? parentWatcher;
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
        watcher.Error += (_, value) => Report(value.GetException() is not InternalBufferOverflowException);
        try
        {
            // A directory handle can keep following its inode after a rename. Observe the
            // selected name in its parent as well; never silently watch a different path.
            string normalized = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
            if (Directory.GetParent(normalized) is { } parent)
            {
                parentWatcher = new(parent.FullName)
                {
                    Filter = Path.GetFileName(normalized),
                    NotifyFilter = NotifyFilters.DirectoryName
                };
                parentWatcher.Deleted += (_, _) => Report(true);
                parentWatcher.Renamed += (_, _) => Report(true);
                // Lost parent events also lose proof of the selected directory's identity.
                parentWatcher.Error += (_, _) => Report(true);
                parentWatcher.EnableRaisingEvents = true;
            }
            watcher.EnableRaisingEvents = true;
            if (!Directory.Exists(root)) throw new IOException("library-watch-root");
        }
        catch { parentWatcher?.Dispose(); watcher.Dispose(); throw; }
    }
    private void Report(bool unavailable)
    {
        lock (gate)
        {
            if (stopped || failed) return;
            // A lost content buffer requires a completed scan, never partial event replay.
            failed = unavailable;
            events.Writer.TryWrite(failed ? LibraryMonitorEvent.Unavailable : LibraryMonitorEvent.Changed);
            if (failed) events.Writer.TryComplete();
        }
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
        parentWatcher?.Dispose(); watcher.Dispose();
    }
}
