using System.Diagnostics;
using System.IO;
using SyncWatch.Domain;
using SyncWatch.Library;
using SyncWatch.Playback;

namespace SyncWatch;

// A serialized, silent paused VLC owner; no watch state, surface or room authority.
internal sealed class LibraryMetadataReader(MediaConfiguration media) : IMediaMetadataReader
{
    private readonly VLCPlayback player = new();
    private readonly SemaphoreSlim serial = new(1, 1);
    private readonly string runId = "metadata-" + Guid.NewGuid().ToString("D");
    private ulong generation;
    private bool opened, closed;
    public async Task<MediaMetadata> ReadAsync(LocalMediaFile file, CancellationToken cancellation)
    {
        await serial.WaitAsync(cancellation);
        PlaybackScope? scope = null;
        try
        {
            if (closed) throw new ObjectDisposedException(nameof(LibraryMetadataReader));
            if (!opened) { await player.OpenAsync(media.Bridge, media.Package, cancellation: cancellation); opened = true; }
            cancellation.ThrowIfCancellationRequested();
            scope = new PlaybackScope(runId, ++generation);
            await player.LoadAsync(file.File, scope, cancellation);
            var version = await player.ContentVersionAsync(scope, cancellation);
            if (version.SizeBytes != file.SizeBytes) throw new IOException("metadata-input-changed");
            var clock = Stopwatch.StartNew();
            MediaMetadata? result = null;
            while (clock.Elapsed < TimeSpan.FromSeconds(3))
            {
                cancellation.ThrowIfCancellationRequested();
                var value = await player.ObserveAsync(scope, cancellation);
                if (value.Status == PlaybackStatus.Failed) throw new IOException("metadata-unavailable");
                if (value.Status == PlaybackStatus.Ready && !value.Buffering)
                {
                    var audio = await player.TracksAsync(false, scope, cancellation);
                    var subtitles = await player.TracksAsync(true, scope, cancellation);
                    result = new(value.DurationMs, value.Width, value.Height,
                        audio.Count(track => track.Id >= 0), subtitles.Count(track => track.Id >= 0),
                        audio.Where(track => track.Id >= 0).Select(track => track.Name).ToArray(),
                        subtitles.Where(track => track.Id >= 0).Select(track => track.Name).ToArray());
                    if (value.DurationMs is not null && value.Width > 0 && value.Height > 0) break;
                }
                await Task.Delay(50, cancellation);
            }
            if (result is null) throw new IOException("metadata-unavailable");
            if (!(await player.ContentVersionAsync(scope, cancellation)).Equals(version))
                throw new IOException("metadata-input-changed");
            var facts = new FileInfo(file.File);
            if (!facts.Exists || facts.Length != file.SizeBytes || facts.LastWriteTimeUtc != file.ModificationDate.UtcDateTime)
                throw new IOException("metadata-input-changed");
            return result;
        }
        finally
        {
            if (scope is not null) { try { await player.StopAsync(scope); } catch (Exception) { } }
            serial.Release();
        }
    }
    public async Task CloseAsync()
    {
        await serial.WaitAsync();
        try { closed = true; await player.DisposeAsync(); }
        finally { serial.Release(); }
    }
}
