using System.Windows.Controls;

namespace SyncWatch.Design;

public enum LibraryVisualState { Empty, Scanning, Selected, MissingMedia, Reconnecting }

public sealed record LibraryEntry(string Id, string Title, string Location);

// Presentation/capabilities only: no filesystem, media engine, call or network dependency.
public sealed record LibraryPresentation
{
    public long? MetadataDurationMs { get; init; }
    public int MetadataWidth { get; init; }
    public int MetadataHeight { get; init; }
    public int? MetadataAudioTracks { get; init; }
    public int? MetadataSubtitleTracks { get; init; }
    public bool MetadataLoading { get; init; }
    public bool MetadataUnavailable { get; init; }
    public string RoomStatus { get; init; } = "";
    public LibraryVisualState State { get; init; }
    public IReadOnlyList<LibraryEntry> Entries { get; init; } = [];
    public string? SelectedId { get; init; }
    public IReadOnlySet<string> EnabledActions { get; init; } = new HashSet<string>();
    public LibraryEntry? Selected => Entries.FirstOrDefault(e => e.Id == SelectedId);

    public bool Allows(string action) => EnabledActions.Contains(action) && SyncWatchCopy.LibraryActions.Contains(action) && (action switch
    {
        "startWatching" => State == LibraryVisualState.Selected && Selected is not null,
        "selectMovie" or "search" => State != LibraryVisualState.Scanning,
        _ => true,
    });

    public void Dispatch(string action, string? value, Action<string, string?> handler)
    {
        if (Allows(action) && (action != "selectMovie" || Entries.Any(e => e.Id == value))) handler(action, value);
    }

    public static LibraryPresentation Gallery(LibraryVisualState state)
    {
        LibraryEntry[] entries = state is LibraryVisualState.Empty or LibraryVisualState.Scanning ? [] :
            SyncWatchCopy.GalleryMovies.Select((title, index) => new LibraryEntry(index.ToString(System.Globalization.CultureInfo.InvariantCulture), title, "Movies/" + title)).ToArray();
        return new LibraryPresentation
        {
            State = state,
            Entries = entries,
            SelectedId = entries.FirstOrDefault()?.Id,
            EnabledActions = new HashSet<string> { "chooseFolder", "rescan", "search", "selectMovie", "startWatching", "openSettings" },
        };
    }
}

public sealed class LibraryWorkspace : UserControl
{
    public LibraryPresentation Presentation { get; private set; } = new();
    public string UiLanguage { get; private set; } = "en";
    public event Action<string, string?>? ActionRequested;
    private readonly DesignSurface surface = new("Library");
    private string query = "";
    public LibraryWorkspace()
    {
        Content = surface; surface.ConfigureHost(this);
        surface.EventRequested += e => { if (e.Action == "search") { query = e.Value ?? ""; Refresh(); } Presentation.Dispatch(e.Action, e.Value, (a, v) => ActionRequested?.Invoke(a, v)); };
        Refresh();
    }
    public void Render(LibraryPresentation presentation, string language = "en") { Presentation = presentation; UiLanguage = language; Refresh(); }
    private void Refresh() => surface.Render(DesignBindings.Library(Presentation, query, UiLanguage), UiLanguage);
}
