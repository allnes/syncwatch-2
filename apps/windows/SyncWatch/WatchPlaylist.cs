using SyncWatch.Design;

namespace SyncWatch;

// Correlates catalog choices with one current watch. Common Design owns rendering.
internal sealed class WatchPlaylist
{
    private readonly string sourceID = "playlist-" + Guid.NewGuid();
    private SelectionMenuPresentation snapshot = new();
    private bool closed;
    internal SelectionMenuPresentation? Menu { get; private set; }
    internal event Action? Changed;

    internal void Update(IReadOnlyList<SelectionMenuEntry> entries, string? selectedID, bool enabled)
    {
        selectedID = entries.Any(entry => entry.Id == selectedID) ? selectedID : null;
        if (closed || (snapshot.Entries.SequenceEqual(entries) && snapshot.SelectedID == selectedID && snapshot.Enabled == enabled)) return;
        if (snapshot.Revision >= SyncWatchSelectionMenu.MaximumRevision) { Close(); return; }
        snapshot = new()
        {
            Kind = "playlist",
            SourceID = sourceID,
            Revision = snapshot.Revision + 1,
            Entries = entries.ToArray(),
            SelectedID = selectedID,
            Enabled = enabled
        };
        Menu = null; Changed?.Invoke();
    }
    internal void Open() { if (closed || !snapshot.IsValid) return; Menu = snapshot; Changed?.Invoke(); }
    internal void Dismiss() { if (Menu is null) return; Menu = null; Changed?.Invoke(); }
    internal void Close() { closed = true; Menu = null; snapshot = new(); Changed?.Invoke(); }
    internal string? Neighbor(int direction)
    {
        if (closed || !snapshot.IsValid || !snapshot.Enabled || direction is not (-1 or 1)) return null;
        int index = Array.FindIndex(snapshot.Entries.ToArray(), entry => entry.Id == snapshot.SelectedID);
        if (index < 0) return null;
        for (int next = index + direction; next >= 0 && next < snapshot.Entries.Count; next += direction)
            if (snapshot.Entries[next].Enabled) return snapshot.Entries[next].Id;
        return null;
    }
    internal string? Selection(SelectionMenuRequest request)
    {
        if (closed || Menu is null || request.Kind != snapshot.Kind || request.Scope != "shared" ||
            request.Action != snapshot.Definition?.Action || request.SourceID != sourceID ||
            request.Revision != snapshot.Revision || Menu.ContextToken != snapshot.ContextToken || !snapshot.Allows(request.EntryID)) return null;
        Dismiss(); return request.EntryID;
    }
    internal PlayerPresentation Presentation(PlayerPresentation source)
    {
        HashSet<string> enabled = new(source.EnabledActions);
        enabled.ExceptWith(["openPlaylist", "previousFile", "nextFile"]);
        bool previous = Neighbor(-1) is not null, next = Neighbor(1) is not null;
        if (!closed && snapshot.IsValid && snapshot.Entries.Count > 0) enabled.Add("openPlaylist");
        if (previous) enabled.Add("previousFile");
        if (next) enabled.Add("nextFile");
        return source with { EnabledActions = enabled, HasPrevious = previous, HasNext = next };
    }
}
