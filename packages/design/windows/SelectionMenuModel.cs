using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace SyncWatch.Design;

public sealed record SelectionMenuEntry(string Id, string Label, bool Enabled = true, bool DisabledTrack = false)
{
    public static SelectionMenuEntry OffTrack => new("-1", "off", DisabledTrack: true);
    public static string ObservedLabel(string name, string language) =>
        name.Length > 0 && Encoding.UTF8.GetByteCount(name) <= SyncWatchSelectionMenu.MaximumLabelBytes && !name.Any(c => c < 32 || c == 127)
            ? name : SyncWatchCopy.Text("unknown", language);
    public static SelectionMenuEntry? ExternalFile(string kind, string language)
    {
        var filter = SyncWatchSelectionMenu.ExternalFileFilters.FirstOrDefault(item => item.Kind == kind);
        return filter is null ? null : new(SyncWatchSelectionMenu.ExternalFileID, SyncWatchCopy.Text(filter.Label, language));
    }
    public static string CompanionLabel(string relativePath, bool duplicate, string language)
    {
        string policy = duplicate ? SyncWatchSelectionMenu.DuplicateCompanionFileLabel : SyncWatchSelectionMenu.CompanionFileLabel;
        return ObservedLabel(policy == "relativePath" ? relativePath : relativePath.Split('/').Last(), language);
    }
    public static SelectionMenuEntry ExternalFileFailure(string language) =>
        new(SyncWatchSelectionMenu.ExternalFileErrorID, SyncWatchCopy.Text(SyncWatchSelectionMenu.ExternalFileErrorLabel, language), Enabled: false);
}
public sealed record SelectionMenuRequest(string Kind, string SourceID, long Revision, string EntryID, string Action, string Scope);

// Provider observations only. Dispatch never changes the observed selection.
public sealed record SelectionMenuPresentation
{
    public string Kind { get; init; } = "playlist";
    public string SourceID { get; init; } = "";
    public long Revision { get; init; }
    public IReadOnlyList<SelectionMenuEntry> Entries { get; init; } = [];
    public string? SelectedID { get; init; }
    public bool Enabled { get; init; }
    public SelectionMenuKind? Definition => SyncWatchSelectionMenu.Kinds.FirstOrDefault(k => k.Id == Kind);
    public string ContextToken => string.Create(CultureInfo.InvariantCulture, $"{Kind}|{SourceID}|{Revision}");
    private static bool ValidID(string value) => value.Length <= SyncWatchSelectionMenu.MaximumIDBytes && Regex.IsMatch(value, @"\A[A-Za-z0-9._:-]+\z");
    private static bool ValidEntry(SelectionMenuEntry entry) =>
        ValidID(entry.Id) && entry.Label.Length > 0
        && Encoding.UTF8.GetByteCount(entry.Label) <= SyncWatchSelectionMenu.MaximumLabelBytes
        && !entry.Label.Any(c => c < 32 || c == 127);
    public bool IsValid => Definition is not null && ValidID(SourceID)
        && Revision is >= 0 and <= SyncWatchSelectionMenu.MaximumRevision
        && Entries.Count <= SyncWatchSelectionMenu.MaximumEntries
        && Entries.Select(e => e.Id).Distinct(StringComparer.Ordinal).Count() == Entries.Count
        && Entries.All(ValidEntry)
        && (SelectedID is null || Entries.Any(e => e.Id == SelectedID));
    public bool Allows(string id) => IsValid && Enabled && id != SelectedID && Entries.Any(e => e.Id == id && e.Enabled);
    public void Dispatch(string id, string contextToken, Action<SelectionMenuRequest> handler)
    {
        if (contextToken != ContextToken || !Allows(id) || Definition is not SelectionMenuKind definition) return;
        handler(new(Kind, SourceID, Revision, id, definition.Action, definition.Scope));
    }
}
