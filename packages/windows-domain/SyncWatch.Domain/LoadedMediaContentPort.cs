namespace SyncWatch.Domain;

/// <summary>Local equality evidence. Never include the opaque stamp in room DTOs or logs.</summary>
public sealed class LoadedMediaVersion : IEquatable<LoadedMediaVersion>
{
    public PlaybackScope Scope { get; }
    public long SizeBytes { get; }
    private readonly string stamp;
    public LoadedMediaVersion(PlaybackScope scope, long sizeBytes, string stamp)
    {
        ArgumentNullException.ThrowIfNull(scope);
        if (sizeBytes < 0 || stamp is null || stamp.Length != 128 || stamp.Any(c => !(c is >= '0' and <= '9' or >= 'a' and <= 'f')))
            throw new ContractException(ContractRejection.Malformed);
        Scope = scope; SizeBytes = sizeBytes; this.stamp = stamp;
    }
    public bool Equals(LoadedMediaVersion? other) => other is not null && Scope == other.Scope && SizeBytes == other.SizeBytes && stamp == other.stamp;
    public override bool Equals(object? obj) => obj is LoadedMediaVersion other && Equals(other);
    public override int GetHashCode() => HashCode.Combine(Scope, SizeBytes, stamp);
    public override string ToString() => "LoadedMediaVersion(redacted)";
}

/// <summary>Reads the player's owned file without resolving another path or moving its stream.</summary>
public interface ILoadedMediaContentPort
{
    Task<LoadedMediaVersion> ContentVersionAsync(PlaybackScope scope, CancellationToken cancellation = default);
    Task<byte[]> ReadContentAsync(long offset, int capacity, PlaybackScope scope, CancellationToken cancellation = default);
}
