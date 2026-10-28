namespace SyncWatch.Library;

// Observed local facts, never shared-edition authorization or peer paths.
public sealed record MediaMetadata
{
    public long? DurationMs { get; }
    public int Width { get; }
    public int Height { get; }
    public int AudioTracks { get; }
    public int SubtitleTracks { get; }
    public IReadOnlyList<string>? AudioTrackNames { get; }
    public IReadOnlyList<string>? SubtitleTrackNames { get; }
    public MediaMetadata(long? durationMs, int width, int height, int audioTracks, int subtitleTracks,
        IReadOnlyList<string>? audioTrackNames = null, IReadOnlyList<string>? subtitleTrackNames = null)
    {
        if (durationMs < 0 || width < 0 || height < 0 || audioTracks < 0 || subtitleTracks < 0)
            throw new ArgumentOutOfRangeException(nameof(durationMs));
        DurationMs = durationMs; Width = width; Height = height;
        AudioTracks = audioTracks; SubtitleTracks = subtitleTracks;
        AudioTrackNames = Names(audioTrackNames, audioTracks);
        SubtitleTrackNames = Names(subtitleTrackNames, subtitleTracks);
    }
    private static IReadOnlyList<string>? Names(IReadOnlyList<string>? names, int count)
    {
        if (names is null) return null;
        var copy = names.ToArray();
        if (copy.Length != count || copy.Any(name => name is null || name.Contains('\0') ||
            System.Text.Encoding.UTF8.GetByteCount(name) > 4096))
            throw new ArgumentException("Invalid observed track names", nameof(names));
        return Array.AsReadOnly(copy);
    }
    public bool Equals(MediaMetadata? other) => other is not null && DurationMs == other.DurationMs &&
        Width == other.Width && Height == other.Height && AudioTracks == other.AudioTracks &&
        SubtitleTracks == other.SubtitleTracks && SameNames(AudioTrackNames, other.AudioTrackNames) &&
        SameNames(SubtitleTrackNames, other.SubtitleTrackNames);
    private static bool SameNames(IReadOnlyList<string>? left, IReadOnlyList<string>? right) =>
        left is null ? right is null : right is not null && left.SequenceEqual(right);
    public override int GetHashCode()
    {
        var hash = new HashCode();
        hash.Add(DurationMs); hash.Add(Width); hash.Add(Height); hash.Add(AudioTracks); hash.Add(SubtitleTracks);
        foreach (var names in new[] { AudioTrackNames, SubtitleTrackNames })
        {
            hash.Add(names is not null);
            if (names is not null) foreach (var name in names) hash.Add(name);
        }
        return hash.ToHashCode();
    }
}

public interface IMediaMetadataReader
{
    Task<MediaMetadata> ReadAsync(LocalMediaFile file, CancellationToken cancellation);
    Task CloseAsync();
}
