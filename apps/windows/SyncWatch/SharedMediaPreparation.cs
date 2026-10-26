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
    private LoadedMediaVersion? prepared;

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
            if (player is not ILoadedMediaContentPort content) throw new InvalidOperationException("media-unavailable");
            var version = await content.ContentVersionAsync(scope, token);
            if (version.SizeBytes != selection.Media.SizeBytes) throw new InvalidOperationException("media-changed");
            string digest = await new FileContentHasher().Sha256Async(version.SizeBytes,
                (offset, capacity, cancellation) => content.ReadContentAsync(offset, capacity, scope, cancellation), token);
            var after = await player.ObserveAsync(scope, token);
            if (after.Status != PlaybackStatus.Ready || !after.Seekable || after.DurationMs != before.DurationMs
                || !version.Equals(await content.ContentVersionAsync(scope, token))) throw new InvalidOperationException("media-changed");
            token.ThrowIfCancellationRequested(); prepared = version;
            string title = MediaDescriptor.LogicalTitle(selection.Media.Title);
            return new(selection.Media.Id, title, MediaDescriptor.NormalizedTitleKey(title), selection.Media.SizeBytes, before.DurationMs, digest);
        }
        finally { GC.KeepAlive(selection.Access); }
    }
    internal async Task ValidateAsync(ILoadedMediaContentPort content, PlaybackScope scope)
    {
        if (closed || prepared is null || prepared.Scope != scope
            || !prepared.Equals(await content.ContentVersionAsync(scope, cancellation.Token))) throw new InvalidOperationException("media-changed");
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
        prepared = null;
        cancellation.Dispose();
    }
}
