using System.IO;
using System.Windows.Threading;
using SyncWatch;
using SyncWatch.Domain;
using SyncWatch.Library;

internal static class LibraryRefreshChecks
{
    private sealed class AccessStore : ILibraryAccessStore
    {
        private readonly object gate = new();
        private LibraryAccessRecord? record;
        private int writes;
        internal int Count { get { lock (gate) return writes; } }
        public LibraryAccessRead Read() { lock (gate) return new(record is null ? LibraryAccessStatus.Missing : LibraryAccessStatus.Loaded, record); }
        public void Write(LibraryAccessRecord value) { lock (gate) { record = value; writes++; } }
    }
    internal static async Task RunAsync()
    {
        string scratch = Path.Combine(Path.GetTempPath(), "syncwatch-library-refresh-" + Guid.NewGuid());
        string first = Path.Combine(scratch, "first"), second = Path.Combine(scratch, "second");
        Directory.CreateDirectory(first); Directory.CreateDirectory(second);
        foreach (string root in new[] { first, second }) File.WriteAllText(Path.Combine(root, "Кино.One.mkv"), "fixture");
        var store = new AccessStore();
        var model = new LibraryController(store, Dispatcher.CurrentDispatcher);
        LibraryController? restored = null;
        static async Task Eventually(Func<bool> condition)
        {
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(8));
            while (!condition()) await Task.Delay(20, deadline.Token);
        }
        static void Require(bool value) { if (!value) throw new InvalidOperationException("library-refresh-acceptance"); }
        try
        {
            Require(model.ConfigureOptions(true, true));
            model.Choose(first); await model.Settled;
            string selected = model.Presentation.SelectedId ?? throw new InvalidOperationException("missing-selection");
            File.WriteAllText(Path.Combine(first, "Кино.Two.mkv"), "fixture");
            await Eventually(() => model.Presentation.Entries.Count == 2);
            Require(model.Presentation.SelectedId == selected && store.Count == 1);
            var roomRevision = model.RoomRevision;
            File.WriteAllText(Path.Combine(first, "Кино.One.en.srt"), "subtitle");
            await Eventually(() => model.SelectedMedia()?.Media.Companions.Count == 1);
            Require(model.RoomRevision == roomRevision && store.Count == 1);
            File.WriteAllText(Path.Combine(first, "old-only.mp4"), "fixture");
            model.Choose(second); await model.Settled;
            File.WriteAllText(Path.Combine(second, "Кино.Two.mkv"), "fixture");
            await Eventually(() => model.Presentation.Entries.Count == 2);
            Require(model.Presentation.Entries.Select(file => file.Title).SequenceEqual(new[] { "Кино.One.mkv", "Кино.Two.mkv" }));
            Require(model.SelectedMedia()?.Access.RootPath == second && store.Count == 2);
            await model.CloseAsync();
            var stateStore = new FileLocalStateStore(Path.Combine(scratch, "options/local-state.json"));
            var preferences = new AppearancePreferences(stateStore);
            Require(preferences.State.Preferences.AutomaticRefresh is null);
            Require(preferences.Save(new Dictionary<string, string> { ["theme"] = "dark", ["language"] = "ru", ["scanSubfolders"] = "true", ["automaticRefresh"] = "false" }, true));
            Require(await preferences.PersistWatchStateAsync(LocalState.CreateDefault()));
            var saved = new AppearancePreferences(stateStore);
            Require(saved.State.Preferences.ScanSubfolders == true && saved.State.Preferences.AutomaticRefresh == false);
            restored = new LibraryController(store, Dispatcher.CurrentDispatcher);
            Require(restored.ConfigureOptions(saved.State.Preferences.ScanSubfolders, saved.State.Preferences.AutomaticRefresh));
            restored.Restore(); await restored.Settled; int writes = store.Count;
            File.WriteAllText(Path.Combine(second, "manual.mp4"), "fixture"); await Task.Delay(1000);
            Require(restored.Presentation.Entries.Count == 2);
            restored.Rescan(); await restored.Settled;
            Require(restored.Presentation.Entries.Count == 3 && store.Count == writes);
            var editor = restored.SettingsEditor(saved.CreateEditor());
            Require(editor.Values["automaticRefresh"] == "false" && editor.EditableFields.Contains("automaticRefresh"));
            editor.Edit("scanSubfolders", "false"); editor.Edit("automaticRefresh", "true");
            Require(editor.Save(values => saved.Save(values, true)));
            Require(restored.ConfigureOptions(saved.State.Preferences.ScanSubfolders, saved.State.Preferences.AutomaticRefresh)); await restored.Settled;
            File.WriteAllText(Path.Combine(second, "live.mp4"), "fixture");
            await Eventually(() => restored.Presentation.Entries.Count == 4);
            string nested = Path.Combine(second, "deep/ignored.mkv"); Directory.CreateDirectory(Path.GetDirectoryName(nested)!); File.WriteAllText(nested, "fixture");
            restored.Rescan(); await restored.Settled;
            Require(restored.Presentation.Entries.Count == 4 && store.Count == writes);
            await restored.CloseAsync(); Require(restored.Presentation.EnabledActions.Count == 0);
        }
        finally
        {
            await model.CloseAsync();
            if (restored is not null) await restored.CloseAsync();
            Directory.Delete(scratch, true);
        }
    }
}
