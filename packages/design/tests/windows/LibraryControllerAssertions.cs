using System.IO;
using System.Windows.Threading;
using SyncWatch;
using SyncWatch.Library;

internal static class LibraryControllerAssertions
{
    internal static void Run()
    {
        var dispatcher = Dispatcher.CurrentDispatcher;
        var previous = SynchronizationContext.Current;
        SynchronizationContext.SetSynchronizationContext(new DispatcherSynchronizationContext(dispatcher));
        var task = CheckAsync(dispatcher);
        var frame = new DispatcherFrame();
        var timeout = new DispatcherTimer { Interval = TimeSpan.FromSeconds(30) };
        timeout.Tick += (_, _) => frame.Continue = false;
        _ = task.ContinueWith(_ => dispatcher.BeginInvoke(() => frame.Continue = false), TaskScheduler.Default);
        try
        {
            timeout.Start(); Dispatcher.PushFrame(frame);
            if (!task.IsCompleted) throw new TimeoutException("application-library");
            task.GetAwaiter().GetResult();
        }
        finally { timeout.Stop(); SynchronizationContext.SetSynchronizationContext(previous); }
    }
    private static async Task CheckAsync(Dispatcher dispatcher)
    {
        string scratch = Path.Combine(Path.GetTempPath(), "syncwatch-application-library-" + Guid.NewGuid().ToString("N"));
        string root = Path.Combine(scratch, "movies"), empty = Path.Combine(scratch, "empty");
        Directory.CreateDirectory(root); Directory.CreateDirectory(empty);
        File.WriteAllText(Path.Combine(root, "A.MKV"), "fixture"); File.WriteAllText(Path.Combine(root, "B.mp4"), "fixture");
        string path = Path.Combine(scratch, "state", "library-access.json");
        var store = new FileLibraryAccessStore(path);
        using var model = new LibraryController(store, dispatcher);
        try
        {
            model.Restore(); await model.Settled; Require(model.Presentation.Entries.Count == 0, "empty-store");
            Require(model.SelectedMedia() is null, "no-selection");
            model.Choose(root); Require(model.SelectedMedia() is null, "scanning-selection"); await model.Settled;
            Require(model.ErrorKey is null && model.Presentation.Entries.Select(x => x.Title).SequenceEqual(new[] { "A.MKV", "B.mp4" }), "catalog");
            var ids = model.Presentation.Entries.Select(x => x.Id).ToArray();
            model.Select(ids.Last());
            var owned = model.SelectedMedia() ?? throw new InvalidOperationException("missing local selection");
            Require(owned.Media.Id == ids.Last() && owned.Media.Title == "B.mp4", "typed-selection");
            model.Rescan(); await model.Settled;
            Require(model.Presentation.SelectedId == ids.Last() && model.Presentation.Entries.Select(x => x.Id).SequenceEqual(ids), "rescan");
            using var restored = new LibraryController(store, dispatcher, ids.Last());
            restored.Restore(); await restored.Settled;
            Require(restored.Presentation.SelectedId == ids.Last() && restored.Presentation.Entries.Select(x => x.Id).SequenceEqual(ids), "restore");
            model.Choose(Path.Combine(root, "absent")); await model.Settled;
            Require(model.ErrorKey == "libraryUnavailable" && model.Presentation.Entries.Select(x => x.Id).SequenceEqual(ids), "failed-selection");
            model.Choose(root); model.Choose(Path.Combine(root, "absent")); await model.Settled;
            Require(model.Presentation.State != SyncWatch.Design.LibraryVisualState.Scanning && model.Presentation.Entries.Select(x => x.Id).SequenceEqual(ids), "failed-replacement-scan");
            model.Choose(root); model.Choose(empty); await model.Settled;
            Require(model.ErrorKey is null && model.Presentation.Entries.Count == 0 && store.Read().Record!.RootPath == empty, "obsolete-scan");
            Require(model.SelectedMedia() is null && owned.Access.RootPath == root, "retained-previous-grant");
            string future = "{\"version\":2,\"future\":true}"; File.WriteAllText(path, future);
            model.Choose(root); await model.Settled;
            Require(model.ErrorKey == "librarySaveFailed" && model.Presentation.Entries.Count == 2 && File.ReadAllText(path) == future, "future-preserved");
            model.Choose(empty); model.Dispose(); await model.Settled;
            Require(model.SelectedMedia() is null && model.Presentation.EnabledActions.Count == 0, "closed-selection");
            Require(File.ReadAllText(owned.Media.File) == "fixture" && owned.Access.RootPath == root, "selection-outlives-controller");
            Require(File.ReadAllText(path) == future, "close-cancels");
            Console.WriteLine("SYNCWATCH_APPLICATION_LIBRARY_OK");
        }
        finally { Directory.Delete(scratch, true); }
    }
    private static void Require(bool value, string message) { if (!value) throw new InvalidOperationException(message); }
}
