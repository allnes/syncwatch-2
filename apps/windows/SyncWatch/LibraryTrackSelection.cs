using SyncWatch.Design;
using SyncWatch.Domain;
using SyncWatch.Library;

namespace SyncWatch;

// Inspector IDs belong to a different VLC input. Transfer ordered names and a local ordinal only.
internal sealed record LocalTrackPreferences(IReadOnlyList<string>? AudioNames = null,
    IReadOnlyList<string>? SubtitleNames = null, int? AudioIndex = null, int? SubtitleIndex = null,
    LocalCompanionFile? AudioFile = null, LocalCompanionFile? SubtitleFile = null)
{
    public int? Resolve(IReadOnlyList<PlaybackTrack> tracks, bool subtitles)
    {
        var expected = subtitles ? SubtitleNames : AudioNames;
        if (expected is null) return null;
        var actual = tracks.Where(t => t.Id >= 0).ToArray();
        if (!actual.Select(t => t.Name).SequenceEqual(expected)) throw new InvalidOperationException("media-tracks-changed");
        if ((subtitles ? SubtitleFile : AudioFile) is not null) return null;
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
    private IReadOnlyList<LocalCompanionFile> Companions { get; init; } = [];
    public LibraryTrackSelection Reset(MediaMetadata? metadata = null, IReadOnlyList<LocalCompanionFile>? companions = null) => Dismiss() with
    {
        Companions = companions ?? [],
        Preferences = new(metadata?.AudioTrackNames, metadata?.SubtitleTrackNames,
            metadata?.AudioTrackNames?.Count > 0 ? 0 : null),
    };
    public string? AudioName => Preferences.AudioFile is { } file ? System.IO.Path.GetFileName(file.File) : Preferences.AudioIndex is int index ? Preferences.AudioNames![index] : null;
    public string? SubtitleName => Preferences.SubtitleFile is { } file ? System.IO.Path.GetFileName(file.File) : Preferences.SubtitleIndex is int index ? Preferences.SubtitleNames![index] : null;
    public bool SubtitlesDisabled => Preferences.SubtitleNames is not null && Preferences.SubtitleIndex is null && Preferences.SubtitleFile is null;
    public LibraryTrackSelection Open(string kind, string language)
    {
        var next = Dismiss();
        if (kind is not ("audio" or "subtitles")) return next;
        var names = kind == "audio" ? Preferences.AudioNames : Preferences.SubtitleNames;
        if (names is null) return next;
        var files = Companions.Where(f => (f.Kind == LibraryCompanionKind.Audio ? "audio" : "subtitles") == kind).ToArray();
        if (names.Count == 0 && files.Length == 0) return next;
        var entries = names.Select((name, index) => new SelectionMenuEntry(
            index.ToString(System.Globalization.CultureInfo.InvariantCulture), name.Length == 0 ? SyncWatchCopy.Text("unknown", language) : name)).ToList();
        foreach (var file in files)
        {
            string filename = System.IO.Path.GetFileName(file.File);
            bool duplicate = files.Count(f => System.IO.Path.GetFileName(f.File) == filename) > 1 || names.Contains(filename);
            entries.Add(new("companion:" + file.Id, SelectionMenuEntry.CompanionLabel(file.RelativePath, duplicate, language)));
        }
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
                SelectedID = (kind == "audio" ? Preferences.AudioFile : Preferences.SubtitleFile) is { } selectedFile ? "companion:" + selectedFile.Id
                : (kind == "audio" ? Preferences.AudioIndex : Preferences.SubtitleIndex)?.ToString(System.Globalization.CultureInfo.InvariantCulture)
                ?? (kind == "subtitles" ? "-1" : null),
            }
        };
    }
    public LibraryTrackSelection Select(SelectionMenuRequest request)
    {
        if (Menu is not { } menu || !menu.Allows(request.EntryID) || request.SourceID != SourceId ||
            request.Revision != Revision || request.Kind != menu.Kind || request.Scope != "local" ||
            request.Action != menu.Definition?.Action) return this;
        var file = Companions.FirstOrDefault(f => "companion:" + f.Id == request.EntryID &&
            (f.Kind == LibraryCompanionKind.Audio ? "audio" : "subtitles") == request.Kind);
        if (file is not null) return Dismiss() with
        {
            Preferences = request.Kind == "audio"
            ? Preferences with { AudioFile = file, AudioIndex = null } : Preferences with { SubtitleFile = file, SubtitleIndex = null }
        };
        if (!int.TryParse(request.EntryID, System.Globalization.NumberStyles.Integer,
                System.Globalization.CultureInfo.InvariantCulture, out int index)) return this;
        return Dismiss() with
        {
            Preferences = request.Kind == "audio" ? Preferences with { AudioIndex = index, AudioFile = null }
            : Preferences with { SubtitleIndex = index < 0 ? null : index, SubtitleFile = null }
        };
    }
    public LibraryTrackSelection Dismiss() => this with { Revision = Revision + 1, Menu = null };
}
