using System.IO;
using System.Text.Json;
using System.Windows;
using SyncWatch.Domain;

namespace SyncWatch;

// Explicit own-application integration check; manual and physical acceptance stay separate.
internal static class WatchAcceptance
{
    public static bool Requested => Environment.GetCommandLineArgs().Contains("--watch-check-report");
    private static void Require(bool value) { if (!value) throw new InvalidOperationException("watch integration"); }
    private static async Task Until(Func<Task<bool>> condition)
    {
        var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(20);
        while (DateTime.UtcNow < deadline) { if (await condition()) return; await Task.Delay(40); }
        throw new TimeoutException("watch integration");
    }
    public static async Task RunAsync(Window window, AppearancePreferences preferences, LibraryController catalog, WatchSessionCoordinator watch)
    {
        if (!Requested) return;
        string[] args = Environment.GetCommandLineArgs();
        string? Value(string flag) { int i = Array.IndexOf(args, flag); return i >= 0 && i + 1 < args.Length ? args[i + 1] : null; }
        string? report = Value("--watch-check-report"), file = Value("--watch-check-media");
        string mode = Value("--watch-check-mode") ?? "normal";
        if (report is null || file is null || Value("--state-directory") is null || File.Exists(report)) { window.Close(); return; }
        Dictionary<string, object> result = new() { ["success"] = false, ["guiObserved"] = false, ["physicalOutputAccepted"] = false, ["applicationBuildReady"] = false };
        try
        {
            result["stage"] = "library";
            if (mode == "missing-runtime")
            {
                Require(Environment.UserInteractive && !watch.RuntimeAvailable && watch.ErrorKey == "playbackFailed" && watch.Player is null);
                Require(!watch.LibraryPresentation(catalog.Presentation).EnabledActions.Contains("startWatching"));
                await watch.CloseAsync(); result["missingRuntimeRejected"] = true; result["success"] = true; result.Remove("stage");
                Finish(window, catalog, report, result); return;
            }
            Require(Environment.UserInteractive && window.IsVisible && watch.RuntimeAvailable && watch.Player is null && !watch.PlayerPresented);
            await catalog.Settled;
            if (catalog.Presentation.Entries.Count == 0) { catalog.Choose(Path.GetDirectoryName(file)!); await catalog.Settled; }
            var entry = catalog.Presentation.Entries.Single(x => x.Title == Path.GetFileName(file));
            catalog.Select(entry.Id);
            var selection = catalog.SelectedMedia() ?? throw new InvalidOperationException("selection");
            long expected = preferences.State.ResumePositionFor(entry.Id);
            result["restoredPositionMs"] = expected;
            if (mode != "normal")
            {
                result["stage"] = mode; watch.Start(selection);
                if (mode == "load-failure")
                {
                    await Until(() => Task.FromResult(watch.Phase == WatchPhase.Ended && watch.Player is null));
                    Require(watch.ErrorKey == "playbackFailed" && !watch.PlayerPresented); result["failedLoadReleased"] = true;
                }
                else if (mode == "close-preparing")
                {
                    await Until(() => Task.FromResult(watch.Player is not null)); Require(watch.Phase == WatchPhase.Preparing);
                    await watch.CloseAsync(); await watch.CloseAsync(); Require(watch.Player is null && !watch.PlayerPresented);
                    result["closeDuringPreparation"] = true;
                }
                else throw new ArgumentException("watch check mode");
                await watch.CloseAsync(); result["success"] = true; result.Remove("stage");
                Finish(window, catalog, report, result); return;
            }
            result["stage"] = "start";
            watch.Start(selection);
            await Until(() => Task.FromResult(watch.Player?.Surface.NativeHandle != 0 && watch.Player is not null && watch.Phase == WatchPhase.Active));
            var player = watch.Player!; var scope = player.Scope; var handle = player.Surface.NativeHandle;
            await Until(async () => { var value = await player.Player.ObserveAsync(scope); return value.Status == PlaybackStatus.Ready && value.Paused && value.Seekable && Math.Abs(value.PositionMs - expected) < 300; });
            watch.Start(selection); Require(ReferenceEquals(watch.Player, player) && watch.Scope == scope);
            player.RequestAction("playPause");
            await Until(async () => (await player.Player.ObserveAsync(scope)).PositionMs >= Math.Max(500, expected + 200));
            result["stage"] = "home-continue";
            player.RequestAction("showLibrary"); Require(!watch.PlayerPresented && ReferenceEquals(watch.Player, player));
            long hidden = (await player.Player.ObserveAsync(scope)).PositionMs;
            await Until(async () => (await player.Player.ObserveAsync(scope)).PositionMs >= hidden + 250);
            watch.ContinueWatching(); Require(watch.PlayerPresented && ReferenceEquals(watch.Player, player) && player.Surface.NativeHandle == handle && watch.Scope == scope);
            player.RequestAction("playPause"); await Until(async () => (await player.Player.ObserveAsync(scope)).Paused);
            player.RequestAction("seek", 1300); await Until(() => Task.FromResult(Math.Abs(watch.PositionMs - 1300) < 200));
            result["stage"] = "end-restart";
            watch.End(); await Until(() => Task.FromResult(watch.Player is null && !preferences.SavingWatchState));
            bool released = false;
            try { _ = await player.Player.ObserveAsync(scope); } catch (Exception) { released = true; }
            Require(released && watch.Scope != scope && !watch.PlayerPresented);
            watch.Start(selection);
            await Until(() => Task.FromResult(watch.Player is not null && watch.Phase == WatchPhase.Active));
            var resumed = watch.Player!; Require(!ReferenceEquals(resumed, player) && resumed.Scope != scope);
            await Until(async () => { var value = await resumed.Player.ObserveAsync(resumed.Scope); return value.Paused && Math.Abs(value.PositionMs - 1300) < 250 && Math.Abs(watch.PositionMs - 1300) < 250; });
            watch.End(); await Until(() => Task.FromResult(watch.Player is null && !preferences.SavingWatchState));
            result["stage"] = "cancel-close";
            watch.Start(selection); watch.End(); await watch.CloseAsync(); await watch.CloseAsync();
            Require(watch.Player is null && !watch.PlayerPresented && Math.Abs(preferences.State.ResumePositionFor(entry.Id) - 1300) < 250);
            foreach (string name in new[] { "sameOwnerHomeContinue", "nativeClockWhileHidden", "endReleasesNative", "resumeAfterNewOwner", "cancelBeforeAllocation", "idempotentClose" }) result[name] = true;
            result["success"] = true; result.Remove("stage");
        }
        catch (Exception error) { result["failure"] = error.ToString(); await watch.CloseAsync(); }
        Finish(window, catalog, report, result);
    }
    private static void Finish(Window window, LibraryController catalog, string report, Dictionary<string, object> result)
    {
        catalog.Dispose();
        File.WriteAllText(report, JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
        window.Close();
    }
}
