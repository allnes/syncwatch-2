using System.IO;
using System.Text;
using System.Windows.Threading;
using SyncWatch.Design;
using SyncWatch.Library;

namespace SyncWatch;

// Local ownership only. A catalog identifier is not proof of identical peer content.
internal sealed record LibraryMediaSelection(LocalMediaFile Media, LibraryFolderAccess Access);

/// <summary>Application state; filesystem, access, persistence and design retain independent owners.</summary>
internal sealed class LibraryController(ILibraryAccessStore store, Dispatcher dispatcher, string? selectedId = null) : IDisposable
{
    private readonly FileSystemLibrary scanner = new();
    private readonly SemaphoreSlim persistence = new(1, 1);
    private CancellationTokenSource? pending;
    private LibraryFolderAccess? grant;
    private IReadOnlyDictionary<string, LocalMediaFile> catalog = new Dictionary<string, LocalMediaFile>();
    private LibraryPresentation? stable;
    private long generation;
    private bool closed;
    public LibraryPresentation Presentation { get; private set; } = new() { EnabledActions = new HashSet<string> { "chooseFolder", "openSettings" } };
    public string? ErrorKey { get; private set; }
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
        Presentation.Dispatch("selectMovie", id, (_, _) => { Presentation = Presentation with { SelectedId = id }; stable = Presentation; Changed?.Invoke(); });
    }
    public LibraryMediaSelection? SelectedMedia()
    {
        dispatcher.VerifyAccess();
        return !closed && Presentation.State == LibraryVisualState.Selected && grant is not null &&
            Presentation.SelectedId is string id && catalog.TryGetValue(id, out var media) ? new(media, grant) : null;
    }
    public void ClearError() => ErrorKey = null;
    public void Dispose()
    {
        dispatcher.VerifyAccess(); closed = true; generation++; pending?.Cancel(); grant = null;
        catalog = new Dictionary<string, LocalMediaFile>();
        Presentation = Presentation with { EnabledActions = new HashSet<string>() };
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
        pending?.Cancel(); pending = new(); long current = ++generation;
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
            if (next is null) { if (generation == current) { Presentation = previous; Changed?.Invoke(); } return; }
            var files = await scanner.ScanAsync(next.RootPath, next.RootId, next.Record.ScanSubfolders, token);
            token.ThrowIfCancellationRequested(); if (closed || generation != current) return;
            var utf8 = Comparer<string>.Create((a, b) => Encoding.UTF8.GetBytes(a).AsSpan().SequenceCompareTo(Encoding.UTF8.GetBytes(b)));
            var rows = files.OrderBy(x => x.Title.ToLowerInvariant(), utf8).ThenBy(x => x.RelativePath, utf8)
                .Select(x => new LibraryEntry(x.Id, x.Title, x.File)).ToArray();
            string? selected = new[] { previous.SelectedId, selectedId }.FirstOrDefault(id => id is not null && rows.Any(x => x.Id == id)) ?? rows.FirstOrDefault()?.Id;
            var nextCatalog = files.ToDictionary(x => x.Id);
            grant = next; catalog = nextCatalog; Presentation = new()
            {
                State = rows.Length == 0 ? LibraryVisualState.Empty : LibraryVisualState.Selected,
                Entries = rows,
                SelectedId = selected,
                EnabledActions = new HashSet<string> { "chooseFolder", "rescan", "search", "selectMovie", "openSettings" }
            };
            stable = Presentation; Changed?.Invoke();
            try { await Storage(() => { store.Write(next.Record); return true; }, token); }
            catch (OperationCanceledException) { }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException or ArgumentException)
            { if (generation == current) { ErrorKey = "librarySaveFailed"; Changed?.Invoke(); } }
        }
        catch (OperationCanceledException) { }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException or ArgumentException)
        { if (!closed && generation == current) { Presentation = previous; ErrorKey = "libraryUnavailable"; Changed?.Invoke(); } }
    }
}
