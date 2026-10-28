namespace SyncWatch.Library;

// Observed local facts, never shared-edition authorization or peer paths.
public sealed record MediaMetadata
{
    public long? DurationMs { get; }
    public int Width { get; }
    public int Height { get; }
    public int AudioTracks { get; }
    public int SubtitleTracks { get; }
    public MediaMetadata(long? durationMs, int width, int height, int audioTracks, int subtitleTracks)
    {
        if (durationMs < 0 || width < 0 || height < 0 || audioTracks < 0 || subtitleTracks < 0)
            throw new ArgumentOutOfRangeException(nameof(durationMs));
        DurationMs = durationMs; Width = width; Height = height;
        AudioTracks = audioTracks; SubtitleTracks = subtitleTracks;
    }
}

public interface IMediaMetadataReader
{
    Task<MediaMetadata> ReadAsync(LocalMediaFile file, CancellationToken cancellation);
    Task CloseAsync();
}
