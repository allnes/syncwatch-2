using SyncWatch.Domain;
using SyncWatch.Library;

namespace SyncWatch;

// Owns cancellable preparation and retains the selected folder grant for its lifetime.
internal sealed class SharedMediaPreparation
{
    private readonly CancellationTokenSource cancellation = new();
    private Task<MediaDescriptor>? pending;
    private CancellationTokenSource? pendingCancellation;
    private bool closed;
    private Task? shutdown;

    internal async Task<MediaDescriptor> PrepareAsync(LibraryMediaSelection selection, IPlaybackPort player, PlaybackScope scope, CancellationToken requestCancellation = default)
    {
        requestCancellation.ThrowIfCancellationRequested();
        if (closed) throw new OperationCanceledException();
        if (pending is not null) return await WaitAsync(pending, pendingCancellation!, requestCancellation);
        using var source = CancellationTokenSource.CreateLinkedTokenSource(cancellation.Token, requestCancellation);
        var task = PrepareCoreAsync(selection, player, scope, source.Token); pending = task; pendingCancellation = source;
        try { return await task; }
        finally { if (ReferenceEquals(pending, task)) { pending = null; pendingCancellation = null; } }
    }
    private async Task<MediaDescriptor> PrepareCoreAsync(LibraryMediaSelection selection, IPlaybackPort player, PlaybackScope scope, CancellationToken token)
    {
        try
        {
            var before = await player.ObserveAsync(scope, token);
            if (before.Status != PlaybackStatus.Ready || !before.Seekable || before.DurationMs is not > 0) throw new InvalidOperationException("media-unavailable");
            string digest = await new FileContentHasher().Sha256Async(selection.Media, token);
            var after = await player.ObserveAsync(scope, token);
            if (after.Status != PlaybackStatus.Ready || !after.Seekable || after.DurationMs != before.DurationMs) throw new InvalidOperationException("media-changed");
            string title = MediaDescriptor.LogicalTitle(selection.Media.Title);
            return new(selection.Media.Id, title, MediaDescriptor.NormalizedTitleKey(title), selection.Media.SizeBytes, before.DurationMs, digest);
        }
        finally { GC.KeepAlive(selection.Access); }
    }
    private static async Task<MediaDescriptor> WaitAsync(Task<MediaDescriptor> task, CancellationTokenSource source, CancellationToken token)
    {
        using var registration = token.Register(() =>
        {
            try { source.Cancel(); }
            catch (ObjectDisposedException) { /* Completion already released this operation. */ }
        });
        return await task;
    }
    internal Task CloseAsync() => shutdown ??= CloseCoreAsync();
    private async Task CloseCoreAsync()
    {
        closed = true; cancellation.Cancel();
        if (pending is not null) { try { await pending; } catch (Exception) { /* The request caller observes its failure. */ } }
        cancellation.Dispose();
    }
}
