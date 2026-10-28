using SyncWatch.Design;
using SyncWatch.Domain;

namespace SyncWatch;

// Movie-local requests; provider observations alone acknowledge selection.
internal sealed class LocalPlaybackTracks(IPlaybackTrackControlPort player, PlaybackScope scope, Action changed)
{
    private readonly string sourceId = "tracks-" + Guid.NewGuid();
    private long revision;
    private bool closed;
    private CancellationTokenSource? cancellation;
    private Task? work;
    public SelectionMenuPresentation? Menu { get; private set; }
    // Validate fresh input lists before either command; admission and controls follow acknowledgement.
    public async Task ApplyInitialAsync(LocalTrackPreferences preferences, CancellationToken token)
    {
        if (closed) throw new OperationCanceledException(token);
        int? audio = preferences.AudioNames is null ? null : preferences.Resolve(await player.TracksAsync(false, scope, token), false);
        int? subtitles = preferences.SubtitleNames is null ? null : preferences.Resolve(await player.TracksAsync(true, scope, token), true);
        foreach (var (id, isSubtitle) in new[] { (audio, false), (subtitles, true) })
        {
            if (id is null) continue;
            token.ThrowIfCancellationRequested();
            if (closed) throw new OperationCanceledException(token);
            await AcknowledgeAsync(id.Value, isSubtitle, token);
        }
    }
    private async Task AcknowledgeAsync(int id, bool subtitles, CancellationToken token)
    {
        if (await player.SelectedTrackAsync(subtitles, scope, token) == id) return;
        await player.SelectTrackAsync(id, subtitles, scope, token);
        using CancellationTokenSource deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        deadline.CancelAfter(TimeSpan.FromSeconds(3));
        while (await player.SelectedTrackAsync(subtitles, scope, deadline.Token) != id)
        {
            if (closed) throw new OperationCanceledException(token);
            await Task.Delay(20, deadline.Token);
        }
    }
    public void Open(string kind)
    {
        if (closed || kind is not ("audio" or "subtitles")) return;
        Dismiss();
        var token = Renew(); long current = revision;
        work = ChainAsync(work, () => ReadAsync(kind, current, token), token);
    }
    private async Task ReadAsync(string kind, long current, CancellationToken token)
    {
        try { Publish(await SnapshotAsync(kind, current, token), current, token); }
        catch (Exception) { Publish(new() { Kind = kind }, current, token); }
    }
    public void Select(SelectionMenuRequest request)
    {
        if (closed || Menu is not { } menu || !menu.Allows(request.EntryID) || request.Scope != "local" ||
            request.Kind != menu.Kind || request.SourceID != sourceId || request.Revision != revision ||
            request.Action != menu.Definition?.Action || !int.TryParse(request.EntryID, System.Globalization.NumberStyles.Integer,
                System.Globalization.CultureInfo.InvariantCulture, out int id)) return;
        revision++; var token = Renew(); long current = revision;
        Menu = menu with { Revision = current, Enabled = false }; changed();
        work = ChainAsync(work, () => SelectAsync(request.Kind, id, current, token), token);
    }
    private static async Task ChainAsync(Task? previous, Func<Task> operation, CancellationToken token)
    {
        if (previous is not null) await previous;
        if (!token.IsCancellationRequested) await operation();
    }
    private async Task SelectAsync(string kind, int id, long current, CancellationToken token)
    {
        try
        {
            bool subtitles = kind == "subtitles";
            await AcknowledgeAsync(id, subtitles, token);
            Publish(await SnapshotAsync(kind, current, token), current, token);
            if (!closed && !token.IsCancellationRequested && current == revision) Dismiss();
        }
        catch (Exception) { Publish(new() { Kind = kind }, current, token); }
    }
    private async Task<SelectionMenuPresentation> SnapshotAsync(string kind, long current, CancellationToken token)
    {
        bool subtitles = kind == "subtitles";
        var tracks = await player.TracksAsync(subtitles, scope, token);
        int selected = await player.SelectedTrackAsync(subtitles, scope, token);
        string Id(int value) => value.ToString(System.Globalization.CultureInfo.InvariantCulture);
        var entries = tracks.Select(t => new SelectionMenuEntry(Id(t.Id), t.Name, DisabledTrack: t.Id < 0)).ToList();
        if (subtitles && !tracks.Any(t => t.Id < 0)) entries.Insert(0, SelectionMenuEntry.OffTrack);
        return new()
        {
            Kind = kind,
            SourceID = sourceId,
            Revision = current,
            Enabled = true,
            Entries = entries,
            SelectedID = entries.Any(t => t.Id == Id(selected)) ? Id(selected) : null,
        };
    }
    private void Publish(SelectionMenuPresentation value, long current, CancellationToken token)
    {
        if (closed || token.IsCancellationRequested || current != revision) return;
        Menu = value; changed();
    }
    private CancellationToken Renew()
    {
        cancellation?.Cancel(); cancellation?.Dispose(); cancellation = new(); return cancellation.Token;
    }
    public void Dismiss() { revision++; cancellation?.Cancel(); Menu = null; changed(); }
    public async Task CloseAsync()
    {
        closed = true; Dismiss();
        if (work is not null) await work;
        cancellation?.Dispose(); cancellation = null;
    }
    internal Task SettledAsync() => work ?? Task.CompletedTask;
}
