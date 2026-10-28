using SyncWatch.Design;
using SyncWatch.Domain;
using SyncWatch.Library;

namespace SyncWatch;

// Inspector IDs belong to a different VLC input. Transfer ordered names and a local ordinal only.
internal sealed record LocalTrackPreferences(IReadOnlyList<string>? AudioNames = null,
    IReadOnlyList<string>? SubtitleNames = null, int? AudioIndex = null, int? SubtitleIndex = null)
{
    public int? Resolve(IReadOnlyList<PlaybackTrack> tracks, bool subtitles)
    {
        var expected = subtitles ? SubtitleNames : AudioNames;
        if (expected is null) return null;
        var actual = tracks.Where(t => t.Id >= 0).ToArray();
        if (!actual.Select(t => t.Name).SequenceEqual(expected)) throw new InvalidOperationException("media-tracks-changed");
        int? index = subtitles ? SubtitleIndex : AudioIndex;
        if (index is null) return subtitles ? -1 : null;
        if (index < 0 || index >= actual.Length) throw new InvalidOperationException("media-tracks-changed");
        return actual[index.Value].Id;
    }
}

// One local draft, scoped to the selected metadata generation, independent of room revisions.
internal sealed record LibraryTrackSelection
{
    private string SourceId { get; init; } = "library-tracks-" + Guid.NewGuid();
    private long Revision { get; init; }
    public LocalTrackPreferences Preferences { get; private init; } = new();
    public SelectionMenuPresentation? Menu { get; private init; }
    public LibraryTrackSelection Reset(MediaMetadata? metadata = null) => Dismiss() with
    {
        Preferences = new(metadata?.AudioTrackNames, metadata?.SubtitleTrackNames,
            metadata?.AudioTrackNames?.Count > 0 ? 0 : null),
    };
    public string? AudioName => Preferences.AudioIndex is int index ? Preferences.AudioNames![index] : null;
    public string? SubtitleName => Preferences.SubtitleIndex is int index ? Preferences.SubtitleNames![index] : null;
    public bool SubtitlesDisabled => Preferences.SubtitleNames is not null && Preferences.SubtitleIndex is null;
    public LibraryTrackSelection Open(string kind, string language)
    {
        var next = Dismiss();
        if (kind is not ("audio" or "subtitles")) return next;
        var names = kind == "audio" ? Preferences.AudioNames : Preferences.SubtitleNames;
        if (names is null || names.Count == 0) return next;
        var entries = names.Select((name, index) => new SelectionMenuEntry(
            index.ToString(System.Globalization.CultureInfo.InvariantCulture), name.Length == 0 ? SyncWatchCopy.Text("unknown", language) : name)).ToList();
        if (kind == "subtitles") entries.Insert(0, SelectionMenuEntry.OffTrack);
        return next with
        {
            Menu = new()
            {
                Kind = kind,
                SourceID = SourceId,
                Revision = next.Revision,
                Entries = entries,
                Enabled = true,
                SelectedID = (kind == "audio" ? Preferences.AudioIndex : Preferences.SubtitleIndex)?.ToString(System.Globalization.CultureInfo.InvariantCulture)
                ?? (kind == "subtitles" ? "-1" : null),
            }
        };
    }
    public LibraryTrackSelection Select(SelectionMenuRequest request)
    {
        if (Menu is not { } menu || !menu.Allows(request.EntryID) || request.SourceID != SourceId ||
            request.Revision != Revision || request.Kind != menu.Kind || request.Scope != "local" ||
            request.Action != menu.Definition?.Action || !int.TryParse(request.EntryID, System.Globalization.NumberStyles.Integer,
                System.Globalization.CultureInfo.InvariantCulture, out int index)) return this;
        return Dismiss() with
        {
            Preferences = request.Kind == "audio" ? Preferences with { AudioIndex = index }
            : Preferences with { SubtitleIndex = index < 0 ? null : index }
        };
    }
    public LibraryTrackSelection Dismiss() => this with { Revision = Revision + 1, Menu = null };
}
