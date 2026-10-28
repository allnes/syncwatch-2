using System.IO;
using System.Text;
using System.Windows.Threading;
using SyncWatch.Design;
using SyncWatch.Library;

namespace SyncWatch;

// Local ownership only. A catalog identifier is not proof of identical peer content.
internal sealed record LibraryMediaSelection(LocalMediaFile Media, LibraryFolderAccess Access, LocalTrackPreferences? TrackPreferences = null)
{
    public LocalTrackPreferences Tracks => TrackPreferences ?? new();
}

/// <summary>Application state; filesystem, access, persistence and design retain independent owners.</summary>
internal sealed class LibraryController(ILibraryAccessStore store, Dispatcher dispatcher, string? selectedId = null, IMediaMetadataReader? metadata = null) : IDisposable
{
    private readonly FileSystemLibrary scanner = new();
    private readonly LibraryDurationCache durations = new();
    private readonly SemaphoreSlim persistence = new(1, 1);
    private CancellationTokenSource? pending;
    private CancellationTokenSource? metadataCancellation;
    private long metadataGeneration;
    public Task MetadataSettled { get; private set; } = Task.CompletedTask;
    private LibraryFolderAccess? grant;
    private IReadOnlyDictionary<string, LocalMediaFile> catalog = new Dictionary<string, LocalMediaFile>();
    private LibraryPresentation? stable;
    private long generation;
    private bool closed;
    public LibraryPresentation Presentation { get; private set; } = new() { EnabledActions = new HashSet<string> { "chooseFolder", "openSettings" } };
    public LibraryTrackSelection Tracks { get; private set; } = new();
    public string? ErrorKey { get; private set; }
    public Guid RoomRevision { get; private set; } = Guid.NewGuid();
    public IReadOnlyList<LocalMediaFile> RoomFiles => catalog.Values.OrderBy(p => p.Id, StringComparer.Ordinal).ToArray();
    public event Action? Changed;
    public Task Settled { get; private set; } = Task.CompletedTask;

    public void Restore() => Start(async token =>
    {
        LibraryAccessRead value = await Storage(() => store.Read(), token);
        return value.Status switch
        {
            LibraryAccessStatus.Loaded => await Task.Run(() => LibraryFolderAccess.Restore(value.Record!), token),
            LibraryAccessStatus.Missing or LibraryAccessStatus.Invalid => null,
            _ => throw new InvalidOperationException("unsupported-library-version"),
        };
    });
    public void Choose(string path) => Start(token => Task.Run<LibraryFolderAccess?>(() => LibraryFolderAccess.Selected(path), token));
    public void Rescan() { if (grant is not null) { var owner = grant; Start(_ => Task.FromResult<LibraryFolderAccess?>(owner)); } }
    public void Select(string id)
    {
        dispatcher.VerifyAccess(); if (closed) return;
        Presentation.Dispatch("selectMovie", id, (_, _) => { Presentation = Presentation with { SelectedId = id }; StartMetadata(); Changed?.Invoke(); });
    }
    public LibraryMediaSelection? SelectedMedia()
    {
        dispatcher.VerifyAccess();
        return !closed && Presentation.State == LibraryVisualState.Selected && grant is not null &&
            Presentation.SelectedId is string id && catalog.TryGetValue(id, out var media) ? new(media, grant, Tracks.Preferences) : null;
    }
    public void OpenTracks(string kind, string language)
    {
        dispatcher.VerifyAccess();
        if (closed || !Presentation.Allows(kind == "audio" ? "openLibraryAudio" : "openLibrarySubtitles")) return;
        Tracks = Tracks.Open(kind, language); Changed?.Invoke();
    }
    public void SelectTrack(SelectionMenuRequest request)
    {
        dispatcher.VerifyAccess(); if (closed) return;
        Tracks = Tracks.Select(request);
        Presentation = Presentation with { MetadataAudioName = Tracks.AudioName, MetadataSubtitleName = Tracks.SubtitleName,
            MetadataSubtitlesDisabled = Tracks.SubtitlesDisabled };
        stable = Presentation; Changed?.Invoke();
    }
    public void DismissTracks() { if (Tracks.Menu is null) return; Tracks = Tracks.Dismiss(); Changed?.Invoke(); }
    public void ClearError() => ErrorKey = null;
    public void Dispose()
    {
        dispatcher.VerifyAccess(); if (closed) return; closed = true; Tracks = Tracks.Reset(); generation++; pending?.Cancel(); metadataGeneration++; metadataCancellation?.Cancel(); grant = null;
        catalog = new Dictionary<string, LocalMediaFile>(); durations.Clear();
        Presentation = Presentation with { EnabledActions = new HashSet<string>() };
    }

    public async Task CloseAsync()
    {
        Dispose();
        await Settled; await MetadataSettled;
        if (metadata is not null) await metadata.CloseAsync();
        metadataCancellation?.Dispose(); pending?.Dispose();
    }
    private void CancelMetadata()
    {
        metadataGeneration++; metadataCancellation?.Cancel(); Tracks = Tracks.Reset();
        Presentation = Presentation with
        {
            MetadataDurationMs = null,
            MetadataWidth = 0,
            MetadataHeight = 0,
            MetadataAudioTracks = null,
            MetadataSubtitleTracks = null,
            MetadataAudioName = null, MetadataSubtitleName = null, MetadataSubtitlesDisabled = false,
            MetadataLoading = false,
            MetadataUnavailable = false
        };
    }
    private void StartMetadata()
    {
        var previous = MetadataSettled;
        var previousCancellation = metadataCancellation;
        CancelMetadata(); stable = Presentation;
        if (metadata is null || SelectedMedia() is not { } selection) return;
        long current = metadataGeneration;
        metadataCancellation = new();
        Presentation = Presentation with { MetadataLoading = true }; stable = Presentation;
        var files = new[] { selection.Media }.Concat(Presentation.Entries.Select(row => catalog[row.Id]).Where(file => file.Id != selection.Media.Id)).ToArray();
        MetadataSettled = ReadMetadata(previous, previousCancellation, selection, files, current, metadataCancellation.Token);
    }
    private void PublishDuration(long? value, LocalMediaFile file)
    {
        durations.Record(value, file);
        Presentation = Presentation with { Entries = Presentation.Entries.Select(row => row.Id == file.Id ? row with { DurationMs = value } : row).ToArray() };
    }
    private async Task ReadMetadata(Task previous, CancellationTokenSource? previousCancellation,
        LibraryMediaSelection selection, IReadOnlyList<LocalMediaFile> files, long current, CancellationToken token)
    {
        try
        {
            await previous; previousCancellation?.Dispose(); token.ThrowIfCancellationRequested();
            foreach (var file in files)
            {
                token.ThrowIfCancellationRequested(); if (closed || current != metadataGeneration) return;
                bool selected = file.Id == selection.Media.Id;
                if (!selected && durations.Duration(file) is not null) continue;
                try
                {
                    var value = await metadata!.ReadAsync(file, token);
                    token.ThrowIfCancellationRequested(); if (closed || current != metadataGeneration) return;
                    PublishDuration(value.DurationMs, file);
                    if (selected)
                    {
                        Tracks = Tracks.Reset(value);
                        Presentation = Presentation with
                        {
                            MetadataDurationMs = value.DurationMs,
                            MetadataWidth = value.Width,
                            MetadataHeight = value.Height,
                            MetadataAudioTracks = value.AudioTracks,
                            MetadataSubtitleTracks = value.SubtitleTracks,
                            MetadataLoading = false,
                            MetadataAudioName = Tracks.AudioName, MetadataSubtitleName = Tracks.SubtitleName,
                            MetadataSubtitlesDisabled = Tracks.SubtitlesDisabled,
                            EnabledActions = new HashSet<string>(Presentation.EnabledActions.Concat(["openLibraryAudio", "openLibrarySubtitles"]))
                        };
                    }
                    stable = Presentation; Changed?.Invoke();
                }
                catch (OperationCanceledException) { return; }
                catch (Exception)
                {
                    if (closed || current != metadataGeneration) return;
                    PublishDuration(null, file);
                    if (selected) Presentation = Presentation with { MetadataLoading = false, MetadataUnavailable = true };
                    stable = Presentation; Changed?.Invoke();
                }
            }
        }
        catch (OperationCanceledException) { }
        finally { GC.KeepAlive(selection.Access); }
    }

    private async Task<T> Storage<T>(Func<T> operation, CancellationToken token)
    {
        await persistence.WaitAsync(token);
        try { return await Task.Run(operation, token); }
        finally { persistence.Release(); }
    }
    private void Start(Func<CancellationToken, Task<LibraryFolderAccess?>> acquire)
    {
        dispatcher.VerifyAccess(); if (closed) return;
        pending?.Cancel(); CancelMetadata(); pending = new(); long current = ++generation;
        Settled = Scan(acquire, pending.Token, current);
    }
    private async Task Scan(Func<CancellationToken, Task<LibraryFolderAccess?>> acquire, CancellationToken token, long current)
    {
        var previous = stable ?? Presentation; stable = previous; ErrorKey = null;
        Presentation = previous with { State = LibraryVisualState.Scanning }; Changed?.Invoke();
        try
        {
            var next = await acquire(token);
            token.ThrowIfCancellationRequested();
            if (next is null) { if (generation == current) { Presentation = previous; StartMetadata(); Changed?.Invoke(); } return; }
            var files = await scanner.ScanAsync(next.RootPath, next.RootId, next.Record.ScanSubfolders, token);
            token.ThrowIfCancellationRequested(); if (closed || generation != current) return;
            var utf8 = Comparer<string>.Create((a, b) => Encoding.UTF8.GetBytes(a).AsSpan().SequenceCompareTo(Encoding.UTF8.GetBytes(b)));
            durations.Reconcile(files);
            var rows = files.OrderBy(x => x.Title.ToLowerInvariant(), utf8).ThenBy(x => x.RelativePath, utf8)
                .Select(x => new LibraryEntry(x.Id, x.Title, x.File, durations.Duration(x))).ToArray();
            string? selected = new[] { previous.SelectedId, selectedId }.FirstOrDefault(id => id is not null && rows.Any(x => x.Id == id)) ?? rows.FirstOrDefault()?.Id;
            var nextCatalog = files.ToDictionary(x => x.Id);
            grant = next; catalog = nextCatalog; RoomRevision = Guid.NewGuid(); Presentation = new()
            {
                State = rows.Length == 0 ? LibraryVisualState.Empty : LibraryVisualState.Selected,
                Entries = rows,
                SelectedId = selected,
                EnabledActions = new HashSet<string> { "chooseFolder", "rescan", "search", "selectMovie", "openSettings" }
            };
            StartMetadata(); Changed?.Invoke();
            try { await Storage(() => { store.Write(next.Record); return true; }, token); }
            catch (OperationCanceledException) { }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException or ArgumentException)
            { if (generation == current) { ErrorKey = "librarySaveFailed"; Changed?.Invoke(); } }
        }
        catch (OperationCanceledException) { }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException or ArgumentException)
        { if (!closed && generation == current) { Presentation = previous; StartMetadata(); ErrorKey = "libraryUnavailable"; Changed?.Invoke(); } }
    }
}
