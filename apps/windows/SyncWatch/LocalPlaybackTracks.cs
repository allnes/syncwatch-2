using SyncWatch.Design;
using SyncWatch.Domain;
using SyncWatch.Library;

namespace SyncWatch;

// Movie-local requests; provider observations alone acknowledge selection.
internal sealed class LocalPlaybackTracks(IPlaybackTrackControlPort player, PlaybackScope scope, Action changed,
    IExternalTrackChoosing? picker = null)
{
    private readonly string sourceId = "tracks-" + Guid.NewGuid();
    private long revision;
    private bool closed;
    private CancellationTokenSource? cancellation;
    private Task? work;
    private string language = "en";
    private readonly List<LocalFileAccess> externalFiles = [];
    private readonly Dictionary<(string Kind, int Id), string> aliases = [];
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
    public void Open(string kind, string language = "en")
    {
        if (closed || kind is not ("audio" or "subtitles")) return;
        Dismiss();
        this.language = language;
        var token = Renew(); long current = revision;
        work = ChainAsync(work, () => ReadAsync(kind, current, token), token);
    }
    private async Task ReadAsync(string kind, long current, CancellationToken token)
    {
        try { Publish(await SnapshotAsync(kind, current, token), current, token); }
        catch (Exception) { await UnavailableAsync(kind, current, token); }
    }
    public void Select(SelectionMenuRequest request)
    {
        if (closed || Menu is not { } menu || !menu.Allows(request.EntryID) || request.Scope != "local" ||
            request.Kind != menu.Kind || request.SourceID != sourceId || request.Revision != revision ||
            request.Action != menu.Definition?.Action || (request.EntryID != SyncWatchSelectionMenu.ExternalFileID &&
                !int.TryParse(request.EntryID, System.Globalization.NumberStyles.Integer,
                    System.Globalization.CultureInfo.InvariantCulture, out _))) return;
        revision++; var token = Renew(); long current = revision;
        Menu = menu with { Revision = current, Enabled = false }; changed();
        work = ChainAsync(work, () => SelectAsync(request.Kind, request.EntryID, current, token), token);
    }
    private static async Task ChainAsync(Task? previous, Func<Task> operation, CancellationToken token)
    {
        if (previous is not null) await previous;
        if (!token.IsCancellationRequested) await operation();
    }
    private async Task SelectAsync(string kind, string entryId, long current, CancellationToken token)
    {
        try
        {
            bool subtitles = kind == "subtitles";
            if (entryId == SyncWatchSelectionMenu.ExternalFileID)
            {
                if (picker is null || player is not IPlaybackExternalTrackPort external) throw new InvalidOperationException("external-unavailable");
                var file = await picker.ChooseAsync(kind, language, token);
                token.ThrowIfCancellationRequested();
                if (closed || current != revision) return;
                if (file is null) { Publish(await SnapshotAsync(kind, current, token), current, token); return; }
                externalFiles.Add(file);
                var previous = (await player.TracksAsync(subtitles, scope, token)).Select(t => t.Id).ToHashSet();
                await external.AttachTrackAsync(file.File, subtitles, scope, token);
                int id = await AttachmentAsync(subtitles, previous, token);
                aliases[(kind, id)] = System.IO.Path.GetFileName(file.File);
            }
            else await AcknowledgeAsync(int.Parse(entryId, System.Globalization.CultureInfo.InvariantCulture), subtitles, token);
            Publish(await SnapshotAsync(kind, current, token), current, token);
            if (!closed && !token.IsCancellationRequested && current == revision) Dismiss();
        }
        catch (Exception) { await UnavailableAsync(kind, current, token); }
    }
    private async Task<int> AttachmentAsync(bool subtitles, HashSet<int> previous, CancellationToken token)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        deadline.CancelAfter(TimeSpan.FromSeconds(3));
        while (true)
        {
            deadline.Token.ThrowIfCancellationRequested();
            if (closed) throw new OperationCanceledException(token);
            int id = await player.SelectedTrackAsync(subtitles, scope, deadline.Token);
            if (id >= 0 && !previous.Contains(id) && (await player.TracksAsync(subtitles, scope, deadline.Token)).Any(t => t.Id == id)) return id;
            await Task.Delay(20, deadline.Token);
        }
    }
    private async Task<SelectionMenuPresentation> SnapshotAsync(string kind, long current, CancellationToken token)
    {
        bool subtitles = kind == "subtitles";
        var tracks = await player.TracksAsync(subtitles, scope, token);
        int selected = await player.SelectedTrackAsync(subtitles, scope, token);
        string Id(int value) => value.ToString(System.Globalization.CultureInfo.InvariantCulture);
        var entries = tracks.Select(t => new SelectionMenuEntry(Id(t.Id), SelectionMenuEntry.ObservedLabel(aliases.GetValueOrDefault((kind, t.Id), t.Name), language), DisabledTrack: t.Id < 0)).ToList();
        if (subtitles && !tracks.Any(t => t.Id < 0)) entries.Insert(0, SelectionMenuEntry.OffTrack);
        if (picker is not null && player is IPlaybackExternalTrackPort && entries.Count < SyncWatchSelectionMenu.MaximumEntries &&
            SelectionMenuEntry.ExternalFile(kind, language) is { } fileEntry) entries.Add(fileEntry);
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
    private async Task UnavailableAsync(string kind, long current, CancellationToken token)
    {
        if (closed || token.IsCancellationRequested || current != revision) return;
        if (picker is null || player is not IPlaybackExternalTrackPort)
        {
            Publish(new() { Kind = kind }, current, token);
            return;
        }
        SelectionMenuPresentation value;
        try { value = await SnapshotAsync(kind, current, token); }
        catch { value = new() { Kind = kind, SourceID = sourceId, Revision = current }; }
        if (picker is not null && player is IPlaybackExternalTrackPort)
        {
            var entries = value.Entries.ToList();
            if (entries.Count == 0 && SelectionMenuEntry.ExternalFile(kind, language) is { } fileEntry) entries.Add(fileEntry);
            entries.Insert(0, SelectionMenuEntry.ExternalFileFailure(language));
            value = value with { Entries = entries, Enabled = true };
        }
        Publish(value, current, token);
    }
    private CancellationToken Renew()
    {
        cancellation?.Cancel(); cancellation?.Dispose(); cancellation = new(); return cancellation.Token;
    }
    public void Dismiss() { revision++; cancellation?.Cancel(); picker?.Cancel(); Menu = null; changed(); }
    public async Task CloseAsync()
    {
        closed = true; Dismiss();
        if (work is not null) await work;
        cancellation?.Dispose(); cancellation = null;
    }
    internal Task SettledAsync() => work ?? Task.CompletedTask;
    // The owning workspace calls this after native DisposeAsync has joined all borrowers.
    internal void ReleaseExternalAccess() { externalFiles.Clear(); aliases.Clear(); }
}
