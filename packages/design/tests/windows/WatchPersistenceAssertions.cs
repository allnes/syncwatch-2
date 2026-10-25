using System.IO;
using System.Windows.Threading;
using SyncWatch;
using SyncWatch.Domain;

internal static class WatchPersistenceAssertions
{
    private sealed class GatedDiskStore(string path) : ILocalStateStore, IDisposable
    {
        private readonly FileLocalStateStore disk = new(path);
        private int first = 1;
        public ManualResetEventSlim Entered { get; } = new();
        public ManualResetEventSlim Proceed { get; } = new();
        public LocalStateRead Read() => disk.Read();
        public void Write(LocalState state)
        {
            if (Interlocked.Exchange(ref first, 0) == 1)
            {
                Entered.Set();
                if (!Proceed.Wait(TimeSpan.FromSeconds(15))) throw new IOException("checkpoint worker timeout");
            }
            disk.Write(state);
        }
        public void Dispose() { Entered.Dispose(); Proceed.Dispose(); }
    }
    public static void Run()
    {
        var dispatcher = Dispatcher.CurrentDispatcher;
        var previous = SynchronizationContext.Current;
        SynchronizationContext.SetSynchronizationContext(new DispatcherSynchronizationContext(dispatcher));
        var frame = new DispatcherFrame();
        var timeout = new DispatcherTimer { Interval = TimeSpan.FromSeconds(30) };
        timeout.Tick += (_, _) => frame.Continue = false;
        var task = CheckAsync();
        _ = task.ContinueWith(_ => dispatcher.BeginInvoke(() => frame.Continue = false), TaskScheduler.Default);
        try
        {
            timeout.Start(); Dispatcher.PushFrame(frame);
            if (!task.IsCompleted) throw new TimeoutException("watch persistence");
            task.GetAwaiter().GetResult();
        }
        finally { timeout.Stop(); SynchronizationContext.SetSynchronizationContext(previous); }
    }
    private static async Task CheckAsync()
    {
        string directory = Path.Combine(Path.GetTempPath(), "syncwatch-watch-persistence-" + Guid.NewGuid().ToString("N"));
        string path = Path.Combine(directory, "local-state.json");
        using var gate = new GatedDiskStore(path);
        Task<bool>? writing = null;
        try
        {
            var preferences = new AppearancePreferences(gate);
            var snapshot = LocalState.CreateDefault() with { SelectedMediaId = "movie-1", ResumePositions = [new ResumePosition { MediaId = "movie-1", PositionMs = 1234 }] };
            writing = preferences.PersistWatchStateAsync(snapshot);
            Check(await Task.Run(() => gate.Entered.Wait(TimeSpan.FromSeconds(15))), "write started");
            Check(preferences.SavingWatchState && !preferences.CreateEditor().CanSave, "appearance capabilities during write");
            Check(!preferences.Save(new Dictionary<string, string> { ["theme"] = "dark", ["language"] = "ru" }), "no false save acknowledgement");
            Check(!await preferences.PersistWatchStateAsync(snapshot), "second writer rejected");
            gate.Proceed.Set();
            Check(await writing && !preferences.SavingWatchState, "write completed");
            Check(preferences.Save(new Dictionary<string, string> { ["theme"] = "dark", ["language"] = "ru" }), "appearance saved after checkpoint");
            Check(await preferences.PersistWatchStateAsync(snapshot), "stale session checkpoint");
            var disk = new FileLocalStateStore(path);
            var restored = new AppearancePreferences(disk).State;
            Check(restored.Preferences.Theme == "dark" && restored.Preferences.Language == "ru", "current appearance wins");
            Check(restored.SelectedMediaId == snapshot.SelectedMediaId && restored.ResumePositions.SequenceEqual(snapshot.ResumePositions), "selected movie and resume roundtrip");
            const string future = "{\"version\":2,\"future\":true}";
            File.WriteAllText(path, future);
            Check(!await preferences.PersistWatchStateAsync(snapshot) && File.ReadAllText(path) == future, "cached owner preserves future file");
            var fresh = new AppearancePreferences(disk);
            Check(!await fresh.PersistWatchStateAsync(snapshot), "fresh owner readonly");
            Check(!fresh.Save(new Dictionary<string, string> { ["theme"] = "light", ["language"] = "en" }) && File.ReadAllText(path) == future, "future bytes preserved");
            Console.WriteLine("SYNCWATCH_WATCH_PERSISTENCE_OK");
        }
        finally
        {
            gate.Proceed.Set();
            if (writing is not null) await writing;
            if (Directory.Exists(directory)) Directory.Delete(directory, true);
        }
    }
    private static void Check(bool value, string message) { if (!value) throw new InvalidOperationException("Watch persistence: " + message); }
}
