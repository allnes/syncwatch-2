using System.IO;
using SyncWatch.Design;
using SyncWatch.Domain;

namespace SyncWatch;

public sealed class AppearancePreferences
{
    private readonly ILocalStateStore store;
    public LocalState State { get; private set; } = LocalState.CreateDefault();
    public bool CanWrite { get; }
    public static string DefaultPath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SyncWatch", "local-state.json");

    public AppearancePreferences(ILocalStateStore store)
    {
        this.store = store;
        try
        {
            var loaded = store.Read();
            if (loaded.Status == LocalStateStatus.Loaded && loaded.State is not null)
            {
                loaded.State.Validate(); State = loaded.State; CanWrite = true;
            }
            else CanWrite = loaded.Status is LocalStateStatus.Missing or LocalStateStatus.Invalid;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or WatchException or ContractException) { CanWrite = false; }
    }

    public SettingsEditor CreateEditor() => new(new Dictionary<string, string> { ["theme"] = State.Preferences.Theme, ["language"] = State.Preferences.Language }, CanWrite ? ["theme", "language"] : [], CanWrite);

    public bool Save(IReadOnlyDictionary<string, string> values)
    {
        if (!CanWrite || !values.TryGetValue("theme", out var theme) || !values.TryGetValue("language", out var language)) return false;
        var next = State with { Preferences = State.Preferences with { Theme = theme, Language = language } };
        try { next.Validate(); store.Write(next); State = next; return true; }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or WatchException or ContractException) { return false; }
    }
}
