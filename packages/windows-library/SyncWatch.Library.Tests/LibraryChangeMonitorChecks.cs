using System.Text.Json;
using SyncWatch.Library;

internal static class LibraryChangeMonitorChecks
{
    public static async Task RunAsync(string fixture)
    {
        using var corpus = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(Path.GetDirectoryName(fixture)!, "library-monitor.json")));
        string Value(string name) => corpus.RootElement.GetProperty(name).GetString()!;
        foreach (bool recursive in new[] { false, true })
        {
            string root = Path.Combine(Path.GetTempPath(), "syncwatch-library-monitor-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            using var monitor = new LibraryChangeMonitor(root, recursive);
            using var readerCancellation = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            await using var events = monitor.Changes(readerCancellation.Token).GetAsyncEnumerator();
            var scanner = new FileSystemLibrary();
            async Task Reconcile(string[] paths, long? size = null)
            {
                using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(8));
                while (true)
                {
                    var read = events.MoveNextAsync().AsTask();
                    bool available;
                    try { available = await read.WaitAsync(deadline.Token); }
                    catch (OperationCanceledException)
                    {
                        readerCancellation.Cancel();
                        try { await read; } catch (OperationCanceledException) { }
                        throw;
                    }
                    if (!available || events.Current != LibraryMonitorEvent.Changed)
                        throw new InvalidOperationException("library-monitor-ended");
                    var files = await scanner.ScanAsync(root, Value("rootId"), recursive, deadline.Token);
                    if (files.Select(file => file.RelativePath).SequenceEqual(paths) && (size is null || files.FirstOrDefault()?.SizeBytes == size)) return;
                }
            }
            try
            {
                File.WriteAllText(Path.Combine(root, Value("created")), Value("content"));
                await Reconcile([Value("created")]);
                File.Move(Path.Combine(root, Value("created")), Path.Combine(root, Value("renamed")));
                await Reconcile([Value("renamed")]);
                File.WriteAllText(Path.Combine(root, Value("renamed")), Value("replacement"));
                await Reconcile([Value("renamed")], System.Text.Encoding.UTF8.GetByteCount(Value("replacement")));
                string nested = Path.Combine(root, Value("nested"));
                Directory.CreateDirectory(Path.GetDirectoryName(nested)!); File.WriteAllText(nested, Value("content"));
                await Reconcile((recursive ? new[] { Value("nested"), Value("renamed") } : [Value("renamed")]).Order(StringComparer.Ordinal).ToArray());
                File.Delete(Path.Combine(root, Value("renamed")));
                await Reconcile(recursive ? [Value("nested")] : []);
                monitor.Dispose();
                while (await events.MoveNextAsync()) { }
                if (monitor.IsActive) throw new InvalidOperationException("library-monitor-active-after-close");
                File.WriteAllText(Path.Combine(root, Value("created")), Value("content"));
                if (await events.MoveNextAsync()) throw new InvalidOperationException("library-monitor-after-close");
            }
            finally { monitor.Dispose(); Directory.Delete(root, true); }
        }
    }
}
