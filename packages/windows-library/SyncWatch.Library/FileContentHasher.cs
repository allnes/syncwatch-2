using System.Security.Cryptography;

namespace SyncWatch.Library;

/// <summary>Serialized bounded background hashing; the caller retains its folder grant.</summary>
public sealed class FileContentHasher
{
    private sealed record Snapshot(long Size, DateTime Modified, DateTime Created);
    private readonly SemaphoreSlim pending = new(1);

    /// <summary>The caller owns and validates the source version; no path is reopened.</summary>
    public async Task<string> Sha256Async(long sizeBytes, Func<long, int, CancellationToken, Task<byte[]>> readChunk,
        CancellationToken cancellation = default)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(sizeBytes);
        ArgumentNullException.ThrowIfNull(readChunk);
        await pending.WaitAsync(cancellation).ConfigureAwait(false);
        try
        {
            using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            long offset = 0;
            while (offset < sizeBytes)
            {
                cancellation.ThrowIfCancellationRequested();
                int capacity = (int)Math.Min(262_144, sizeBytes - offset);
                byte[] chunk = await readChunk(offset, capacity, cancellation).ConfigureAwait(false);
                if (chunk.Length == 0 || chunk.Length > capacity) throw new IOException("media-changed");
                hash.AppendData(chunk); offset += chunk.Length;
            }
            cancellation.ThrowIfCancellationRequested();
            if ((await readChunk(sizeBytes, 1, cancellation).ConfigureAwait(false)).Length != 0) throw new IOException("media-changed");
            cancellation.ThrowIfCancellationRequested();
            return Convert.ToHexStringLower(hash.GetHashAndReset());
        }
        finally { pending.Release(); }
    }

    public async Task<string> Sha256Async(LocalMediaFile media, CancellationToken cancellation = default)
    {
        await pending.WaitAsync(cancellation).ConfigureAwait(false);
        try { return await Task.Run(() => Hash(media, cancellation), cancellation).ConfigureAwait(false); }
        finally { pending.Release(); }
    }
    private string Hash(LocalMediaFile media, CancellationToken cancellation)
    {
        cancellation.ThrowIfCancellationRequested();
        static void Regular(string path)
        {
            if ((File.GetAttributes(path) & (FileAttributes.Directory | FileAttributes.ReparsePoint)) != 0)
                throw new IOException("media-changed");
        }
        Regular(media.File);
        // On Windows, exclude concurrent writers and replacement for this read lifetime.
        using var file = new FileStream(media.File, FileMode.Open, FileAccess.Read, FileShare.Read, 262_144, FileOptions.SequentialScan);
        Snapshot Current() => new(file.Length, File.GetLastWriteTimeUtc(file.SafeFileHandle), File.GetCreationTimeUtc(file.SafeFileHandle));
        var before = Current();
        if (before.Size != media.SizeBytes || before.Modified != media.ModificationDate.UtcDateTime)
            throw new IOException("media-changed");
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        byte[] buffer = new byte[262_144]; long total = 0;
        for (int count; (count = file.Read(buffer)) != 0;)
        {
            cancellation.ThrowIfCancellationRequested(); total += count;
            if (total > before.Size) throw new IOException("media-changed");
            hash.AppendData(buffer, 0, count);
        }
        cancellation.ThrowIfCancellationRequested(); Regular(media.File);
        if (total != before.Size || Current() != before) throw new IOException("media-changed");
        string digest = Convert.ToHexStringLower(hash.GetHashAndReset());
        return digest;
    }
}
