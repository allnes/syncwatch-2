namespace SyncWatch.Domain;

public enum PlaybackStatus { Unloaded, Loading, Ready, Failed }

public sealed record PlaybackObservation
{
    public required PlaybackScope Scope { get; init; }
    public ulong Sequence { get; init; }
    public PlaybackStatus Status { get; init; }
    public long PositionMs { get; init; }
    public long? DurationMs { get; init; }
    public bool Paused { get; init; }
    public double Rate { get; init; } = 1;
    public bool Seekable { get; init; }
    public bool Buffering { get; init; }
    public bool Ended { get; init; }
    public int Width { get; init; }
    public int Height { get; init; }
    public int VideoOutputs { get; init; }
    public double? Volume { get; init; }
    public bool Muted { get; init; }

    public void Validate()
    {
        if (!Enum.IsDefined(Status) || PositionMs is < 0 or > WatchSession.MaximumPositionMs
            || DurationMs is long duration && (duration is < 0 or > WatchSession.MaximumPositionMs || PositionMs > duration)
            || !double.IsFinite(Rate) || Rate is < .25 or > 4 || Width < 0 || Height < 0 || VideoOutputs < 0
            || Volume is double volume && (!double.IsFinite(volume) || volume is < 0 or > 1)
            || Status != PlaybackStatus.Ready && (!Paused || Seekable || Rate != 1)
            || Status == PlaybackStatus.Unloaded && (PositionMs != 0 || DurationMs is not null))
            throw new ContractException(ContractRejection.Malformed);
    }
}

public sealed record PlaybackTrack(int Id, string Name);

/// <summary>Local commands are submissions; observations come from the actual player.</summary>
public interface IPlaybackPort : IAsyncDisposable
{
    Task LoadAsync(string localFile, PlaybackScope scope, CancellationToken cancellation = default);
    Task<PlaybackObservation> ObserveAsync(PlaybackScope scope, CancellationToken cancellation = default);
    Task SetPausedAsync(bool paused, PlaybackScope scope, CancellationToken cancellation = default);
    Task SeekAsync(long positionMs, PlaybackScope scope, CancellationToken cancellation = default);
    Task SetRateAsync(double rate, PlaybackScope scope, CancellationToken cancellation = default);
    Task SetVolumeAsync(double volume, bool muted, PlaybackScope scope, CancellationToken cancellation = default);
    Task<IReadOnlyList<PlaybackTrack>> TracksAsync(bool subtitles, PlaybackScope scope, CancellationToken cancellation = default);
    Task SelectTrackAsync(int id, bool subtitles, PlaybackScope scope, CancellationToken cancellation = default);
    Task StopAsync(PlaybackScope scope, CancellationToken cancellation = default);
}

/// <summary>Observed local track selection; -1 means disabled/no active track.</summary>
public interface IPlaybackTrackControlPort : IPlaybackPort
{
    Task<int> SelectedTrackAsync(bool subtitles, PlaybackScope scope, CancellationToken cancellation = default);
}

/// <summary>Local file attachment submission; selected-ID acknowledgement is separate.</summary>
public interface IPlaybackExternalTrackPort : IPlaybackTrackControlPort
{
    Task AttachTrackAsync(string localFile, bool subtitles, PlaybackScope scope, CancellationToken cancellation = default);
}
