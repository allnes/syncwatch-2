using System.Text.Json;
using SyncWatch.Domain;
using SyncWatch.Playback;

static void Require(bool condition)
{
    if (!condition) throw new InvalidOperationException("native playback observation");
}
static async Task Rejected(Task operation)
{
    try { await operation.WaitAsync(TimeSpan.FromSeconds(20)); }
    catch (Exception error) when (error is PlaybackException or ContractException or ObjectDisposedException or OperationCanceledException) { return; }
    throw new InvalidOperationException("request was accepted");
}
static async Task<PlaybackObservation> Wait(VLCPlayback player, PlaybackScope scope, Func<PlaybackObservation, bool> predicate)
{
    using CancellationTokenSource deadline = new(TimeSpan.FromSeconds(15));
    while (true)
    {
        PlaybackObservation value = await player.ObserveAsync(scope, deadline.Token);
        Require(value.Status != PlaybackStatus.Failed);
        if (predicate(value)) return value;
        await Task.Delay(40, deadline.Token);
    }
}

PlaybackScope scope = new("dotnet-owned-run", 1);
for (int iteration = 0; iteration < 3; iteration++)
{
    VLCPlayback player = new();
    try
    {
        await player.OpenAsync(args[0], args[1]);
        await Rejected(player.LoadAsync(args[2], new("rejected-run", 0)));
        await player.LoadAsync(args[2], scope);
        PlaybackObservation initial = await Wait(player, scope, v => v.Status == PlaybackStatus.Ready && v.Paused && v.Seekable);
        Require(initial.DurationMs == 4000 && initial.PositionMs < 300);
        await player.SetPausedAsync(false, scope);
        PlaybackObservation playing = await Wait(player, scope, v => !v.Paused && v.PositionMs >= 450);
        Require(playing.Sequence > initial.Sequence);
        await player.SetPausedAsync(true, scope);
        PlaybackObservation paused = await Wait(player, scope, v => v.Paused);
        await Task.Delay(250);
        Require(Math.Abs((await player.ObserveAsync(scope)).PositionMs - paused.PositionMs) <= 60);
        await player.SeekAsync(2500, scope);
        await Wait(player, scope, v => v.Paused && v.PositionMs is >= 2300 and <= 2700);
        await player.SeekAsync(250, scope);
        await Wait(player, scope, v => v.Paused && v.PositionMs < 650);
        await player.SetRateAsync(1.25, scope);
        Require((await player.ObserveAsync(scope)).Rate == 1.25);
        await player.SetRateAsync(1, scope);
        IReadOnlyList<PlaybackTrack> audio = await player.TracksAsync(false, scope);
        Require(audio.Any(track => track.Id >= 0 && track.Name.Length > 0));
        await player.SelectTrackAsync(audio.First(track => track.Id >= 0).Id, false, scope);
        await Rejected(player.SetRateAsync(double.NaN, scope));
        await Rejected(player.SeekAsync(5000, scope));
        await Rejected(player.SetPausedAsync(false, new("foreign", 1)));
        using CancellationTokenSource cancelled = new();
        cancelled.Cancel();
        await Rejected(player.StopAsync(scope, cancelled.Token));
        Require((await player.ObserveAsync(scope)).Status == PlaybackStatus.Ready);
        await player.StopAsync(scope);
        await player.StopAsync(scope);
        Require((await player.ObserveAsync(scope)).Status == PlaybackStatus.Unloaded);
        await Rejected(player.SetPausedAsync(false, scope));
        PlaybackScope next = scope.ReplacingMedia();
        await player.LoadAsync(args[2], next);
        await Wait(player, next, v => v.Status == PlaybackStatus.Ready && v.Paused);
        await Rejected(player.ObserveAsync(scope));
        await Rejected(player.LoadAsync(args[2], scope));
    }
    finally { await player.DisposeAsync(); await player.DisposeAsync(); }
    await Rejected(player.ObserveAsync(scope));
}
Console.WriteLine(JsonSerializer.Serialize(new
{
    success = true, ordinaryUtf8Paths = true, nativeClock = true,
    generationTransaction = true, cancellation = true, tracks = true, repeatedClose = true,
    guiAccepted = false, physicalOutputAccepted = false,
}));
