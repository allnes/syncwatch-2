using SyncWatch;
using SyncWatch.Design;
using SyncWatch.Domain;

internal static class LocalPlaybackTracksChecks
{
    private static void Require(bool value) { if (!value) throw new InvalidOperationException("local track ownership"); }
    private static async Task Until(Func<bool> condition)
    {
        using CancellationTokenSource deadline = new(TimeSpan.FromSeconds(2));
        while (!condition()) await Task.Delay(5, deadline.Token);
    }
    internal static async Task RunAsync()
    {
        var player = new TrackPlayer(); var scope = PlaybackScope.Create().ReplacingMedia();
        var model = new LocalPlaybackTracks(player, scope, () => { });
        try
        {
            var invalid = new LocalTrackPreferences(["First", "Second"], ["Changed"], 1);
            bool rejected = false;
            try { await model.ApplyInitialAsync(invalid, default); } catch (InvalidOperationException) { rejected = true; }
            Require(rejected && player.Selections == 0);
            var applying = model.ApplyInitialAsync(new(["First", "Second"], ["First", "Second"], 1), default);
            await Until(() => player.Selections == 1); Require(model.Menu is null && !applying.IsCompleted);
            player.AutoAcknowledge = true; player.Selected = 2; await applying;
            Require(player.Selections == 2 && player.Selected == -1);
            player.AutoAcknowledge = false; player.Selected = 1; player.Selections = 0;
            model.Open("audio"); await model.SettledAsync(); Require(player.LastScope == scope);
            var initial = model.Menu!; SelectionMenuRequest? request = null;
            initial.Dispatch("2", initial.ContextToken, value => request = value);
            model.Select(request!); await Until(() => player.Selections == 1);
            Require(model.Menu is { Enabled: false, SelectedID: "1" });
            player.Selected = 2; await model.SettledAsync(); Require(model.Menu is null);
            model.Open("audio"); await model.SettledAsync(); Require(model.Menu is { Enabled: true, SelectedID: "2" });
            model.Select(request!); Require(player.Selections == 1);
            player.Reject = true;
            var current = model.Menu!; current.Dispatch("1", current.ContextToken, model.Select);
            await model.SettledAsync(); Require(model.Menu is { IsValid: false });
            player.Reject = false; model.Open("subtitles"); await model.SettledAsync();
            Require(model.Menu is { IsValid: true, Kind: "subtitles" });
            player.Hold = new(TaskCreationOptions.RunContinuationsAsynchronously); int before = player.Reads;
            model.Open("audio"); await Until(() => player.Reads == before + 1);
            model.Open("subtitles"); model.Dismiss(); player.Hold.SetResult(); await model.SettledAsync();
            Require(model.Menu is null);
            player.Hold = new(TaskCreationOptions.RunContinuationsAsynchronously);
            model.Open("audio"); await Until(() => player.Reads == before + 2);
            var close = model.CloseAsync(); Require(!close.IsCompleted);
            player.Hold.SetResult(); await close; Require(model.Menu is null);
            model.Open("audio"); Require(model.Menu is null);
        }
        finally { player.Hold?.TrySetResult(); await model.CloseAsync(); }
        Console.WriteLine("SYNCWATCH_LOCAL_TRACKS_OK acknowledgement, stale input, late completion, retry, awaited close");
    }
    private sealed class TrackPlayer : IPlaybackTrackControlPort
    {
        internal int Selected = 1, Selections, Reads;
        internal bool Reject, AutoAcknowledge;
        internal TaskCompletionSource? Hold;
        internal PlaybackScope? LastScope;
        public async Task<IReadOnlyList<PlaybackTrack>> TracksAsync(bool subtitles, PlaybackScope scope, CancellationToken cancellation = default)
        {
            Reads++; LastScope = scope;
            if (Hold is { } hold) await hold.Task; // Deliberately ignore cancellation.
            return [new(-1, "Disable"), new(1, "First"), new(2, "Second")];
        }
        public Task<int> SelectedTrackAsync(bool subtitles, PlaybackScope scope, CancellationToken cancellation = default) => Task.FromResult(Selected);
        public Task SelectTrackAsync(int id, bool subtitles, PlaybackScope scope, CancellationToken cancellation = default)
        { Selections++; if (AutoAcknowledge) Selected = id; return Reject ? Task.FromException(new InvalidOperationException("rejected")) : Task.CompletedTask; }
        public Task LoadAsync(string file, PlaybackScope scope, CancellationToken cancellation = default) => throw new NotSupportedException();
        public Task<PlaybackObservation> ObserveAsync(PlaybackScope scope, CancellationToken cancellation = default) => throw new NotSupportedException();
        public Task SetPausedAsync(bool paused, PlaybackScope scope, CancellationToken cancellation = default) => throw new NotSupportedException();
        public Task SeekAsync(long position, PlaybackScope scope, CancellationToken cancellation = default) => throw new NotSupportedException();
        public Task SetRateAsync(double rate, PlaybackScope scope, CancellationToken cancellation = default) => throw new NotSupportedException();
        public Task SetVolumeAsync(double volume, bool muted, PlaybackScope scope, CancellationToken cancellation = default) => throw new NotSupportedException();
        public Task StopAsync(PlaybackScope scope, CancellationToken cancellation = default) => throw new NotSupportedException();
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
