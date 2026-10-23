using System.Text;
using System.Threading.Channels;
using SyncWatch.Domain;

namespace SyncWatch.Playback;

/// <summary>One bounded worker owns all native calls. No native callback enters managed code.</summary>
public sealed class VLCPlayback : IPlaybackPort
{
    private sealed record Work(Action Run, Action Reject);
    private readonly Channel<Work> commands = Channel.CreateBounded<Work>(new BoundedChannelOptions(64)
    { SingleReader = true, SingleWriter = false, FullMode = BoundedChannelFullMode.Wait });
    private readonly TaskCompletionSource stopped = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private int closing;
    private nint player;
    private PlaybackScope? scope;

    public VLCPlayback()
    {
        Thread worker = new(Run) { IsBackground = true, Name = "SyncWatch playback" };
        worker.Start();
    }
    public Task OpenAsync(string bridge, string package, nint hwnd = 0, CancellationToken cancellation = default) => Submit(() =>
    {
        if (player != 0) throw new PlaybackException("already-open");
        MediaRuntime runtime = MediaRuntime.Verify(package);
        Native.Configure(bridge);
        Native.Check(Native.Open(runtime.Library, runtime.Revision, hwnd == 0 ? 0 : 2, hwnd, out player));
        return true;
    }, cancellation);
    public Task LoadAsync(string localFile, PlaybackScope incoming, CancellationToken cancellation = default) => Submit(() =>
    {
        RequireOpen();
        if (!Path.IsPathFullyQualified(localFile) || !File.Exists(localFile) || new FileInfo(localFile).Attributes.HasFlag(FileAttributes.Directory)) throw new PlaybackException("local-file");
        if (scope is not null)
        {
            if (scope.ClientRunId != incoming.ClientRunId) throw new ContractException(ContractRejection.ForeignRun);
            if (incoming.MediaGeneration <= scope.MediaGeneration) throw new ContractException(ContractRejection.StaleGeneration);
        }
        int result = Native.Load(player, incoming.MediaGeneration, Path.GetFullPath(localFile));
        if (result is 0 or 4) scope = incoming;
        Native.Check(result);
        return true;
    }, cancellation);
    public Task<PlaybackObservation> ObserveAsync(PlaybackScope owner, CancellationToken cancellation = default) => Submit(() =>
    {
        Check(owner); Native.Check(Native.Observe(player, owner.MediaGeneration, out var value));
        var observation = new PlaybackObservation
        {
            Scope = owner,
            Sequence = value.Sequence,
            Status = (PlaybackStatus)value.Status,
            PositionMs = value.PositionMs,
            DurationMs = value.DurationMs < 0 ? null : value.DurationMs,
            Paused = value.Paused != 0,
            Rate = value.Rate,
            Seekable = value.Seekable != 0,
            Buffering = value.Buffering != 0,
            Ended = value.Ended != 0,
            Width = value.Width,
            Height = value.Height,
            VideoOutputs = value.VideoOutputs,
            Volume = value.Volume < 0 ? null : Math.Min(100, value.Volume) / 100d,
            Muted = value.Muted != 0,
        };
        if (value.Generation != owner.MediaGeneration) throw new ContractException(ContractRejection.StaleGeneration);
        observation.Validate(); return observation;
    }, cancellation);
    public Task SetPausedAsync(bool paused, PlaybackScope owner, CancellationToken cancellation = default) => Command(owner, () => Native.Pause(player, owner.MediaGeneration, paused ? 1 : 0), cancellation);
    public Task SeekAsync(long positionMs, PlaybackScope owner, CancellationToken cancellation = default) => Command(owner, () => Native.Seek(player, owner.MediaGeneration, positionMs), cancellation);
    public Task SetRateAsync(double rate, PlaybackScope owner, CancellationToken cancellation = default) => Command(owner, () => Native.Rate(player, owner.MediaGeneration, rate), cancellation);
    public Task SetVolumeAsync(double volume, bool muted, PlaybackScope owner, CancellationToken cancellation = default) => Command(owner, () => Native.Volume(player, owner.MediaGeneration, volume, muted ? 1 : 0), cancellation);
    public Task StopAsync(PlaybackScope owner, CancellationToken cancellation = default) => Command(owner, () => Native.Stop(player, owner.MediaGeneration), cancellation);
    public Task SelectTrackAsync(int id, bool subtitles, PlaybackScope owner, CancellationToken cancellation = default) => Command(owner, () => Native.SelectTrack(player, owner.MediaGeneration, subtitles ? 1 : 0, id), cancellation);
    public Task<IReadOnlyList<PlaybackTrack>> TracksAsync(bool subtitles, PlaybackScope owner, CancellationToken cancellation = default) => Submit<IReadOnlyList<PlaybackTrack>>(() =>
    {
        Check(owner); int[] ids = new int[256];
        Native.Check(Native.Tracks(player, owner.MediaGeneration, subtitles ? 1 : 0, ids, (nuint)ids.Length, out nuint count));
        List<PlaybackTrack> tracks = [];
        for (int index = 0; index < checked((int)count); index++)
        {
            byte[] name = new byte[65_536];
            Native.Check(Native.TrackName(player, owner.MediaGeneration, subtitles ? 1 : 0, ids[index], name, (nuint)name.Length));
            int end = Array.IndexOf(name, (byte)0); if (end < 0) throw new PlaybackException("track-name");
            tracks.Add(new(ids[index], new UTF8Encoding(false, true).GetString(name, 0, end)));
        }
        return tracks;
    }, cancellation);
    private Task Command(PlaybackScope owner, Func<int> command, CancellationToken cancellation) => Submit(() =>
    { Check(owner); Native.Check(command()); return true; }, cancellation);
    private void RequireOpen()
    {
        if (player == 0) throw new PlaybackException("closed");
    }
    private void Check(PlaybackScope owner)
    {
        RequireOpen(); if (scope is null) throw new PlaybackException("unavailable");
        scope.Check(owner.ClientRunId, owner.MediaGeneration);
    }
    private async Task<T> Submit<T>(Func<T> operation, CancellationToken cancellation)
    {
        ObjectDisposedException.ThrowIf(Volatile.Read(ref closing) != 0, this);
        var completion = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        var work = new Work(() =>
        {
            try { cancellation.ThrowIfCancellationRequested(); completion.TrySetResult(operation()); }
            catch (OperationCanceledException) { completion.TrySetCanceled(cancellation); }
            catch (Exception error) { completion.TrySetException(error); }
        }, () => completion.TrySetException(new ObjectDisposedException(nameof(VLCPlayback))));
        await commands.Writer.WriteAsync(work, cancellation).ConfigureAwait(false);
        return await completion.Task.ConfigureAwait(false);
    }
    private void Run()
    {
        try
        {
            while (commands.Reader.WaitToReadAsync().AsTask().GetAwaiter().GetResult())
                while (commands.Reader.TryRead(out Work? work))
                    if (Volatile.Read(ref closing) == 0) work.Run(); else work.Reject();
        }
        finally
        {
            if (player != 0) { Native.Close(player); player = 0; }
            stopped.TrySetResult();
        }
    }
    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref closing, 1) == 0) commands.Writer.TryComplete();
        await stopped.Task.ConfigureAwait(false);
    }
}
