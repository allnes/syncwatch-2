using System.Text.Json;
using SyncWatch.Domain;

internal static class WatchSessionTests
{
    private static readonly JsonSerializerOptions Options = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };

    public static void Run(string corpusDirectory)
    {
        using JsonDocument corpus = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(corpusDirectory, "local-domain.json")));
        Require(corpus.RootElement.GetProperty("formatVersion").GetInt32() == 1, "Unsupported fixture version");
        string directory = Path.Combine(Path.GetTempPath(), $"syncwatch-domain-{Guid.NewGuid():N}");
        Directory.CreateDirectory(directory);
        try
        {
            LocalStateCases(corpus.RootElement, directory);
            LifecycleCases(corpus.RootElement);
            Persistence(directory);
            ResumeHistory();
            PlaylistSelection();
        }
        finally { Directory.Delete(directory, recursive: true); }
        Console.WriteLine("Passed 31 local-state fixtures, 54 lifecycle actions in 6 shared scenarios, persistence recovery, and bounded resume history");
    }

    private static void PlaylistSelection()
    {
        var session = new WatchSession();
        foreach (var (id, position) in new[] { ("first", 12000L), ("second", 24000L) })
        {
            session.Select(id); session.Start(); session.Loaded(session.Scope);
            session.RecordPlayback(session.Scope, position, 60000, true);
        }
        var old = session.Scope;
        Require(session.Select("second").Count == 0, "Repeated selection retains owner");
        var released = session.Select("second", restartFromBeginning: true);
        Require(released.Count == 1 && released[0] == new WatchEffect.Release(old), "Playlist releases the previous owner");
        Require(session.PositionMs == 0 && session.LocalState.ResumePositionFor("second") == 0 && session.LocalState.ResumePositionFor("first") == 12000, "Only the chosen resume resets");
        bool rejected = false;
        try { session.RecordPlayback(old, 50000, 60000, false); } catch (Exception) { rejected = true; }
        Require(rejected && session.Scope != old && session.Phase == WatchPhase.Selected, "Old owner is fenced");
        Require(session.Start().Single() is WatchEffect.Load { Request.PositionMs: 0 }, "Playlist load starts at zero");
        session.Loaded(session.Scope); session.Select("first"); Require(session.PositionMs == 12000, "Other resume retained");
    }

    private static void LocalStateCases(JsonElement corpus, string directory)
    {
        JsonElement fixtures = corpus.GetProperty("localStateCases");
        Require(fixtures.GetArrayLength() == 31, "All local-state fixtures must execute");
        string path = Path.Combine(directory, "formats.json");
        FileLocalStateStore store = new(path);
        Require(store.Read().Status == LocalStateStatus.Missing, "A missing store must remain missing");
        foreach (JsonElement fixture in fixtures.EnumerateArray())
        {
            string json = fixture.TryGetProperty("json", out JsonElement raw) ? raw.GetString()! : fixture.GetProperty("value").GetRawText();
            File.WriteAllText(path, json);
            LocalStateRead result = store.Read();
            string status = Lower(result.Status.ToString());
            Require(status == fixture.GetProperty("status").GetString(), $"Local-state fixture: {fixture.GetProperty("name")}");
            if (result.Status == LocalStateStatus.Loaded)
            {
                LocalState expected = JsonSerializer.Deserialize<LocalState>(json, Options)!;
                Require(EqualState(result.State!, expected), "Loaded state must preserve all preferences and positions");
            }
        }
    }

    private static void LifecycleCases(JsonElement corpus)
    {
        JsonElement fixtures = corpus.GetProperty("lifecycleCases");
        Require(fixtures.GetArrayLength() == 6, "All lifecycle scenarios must execute");
        int actions = 0;
        foreach (JsonElement fixture in fixtures.EnumerateArray())
        {
            ulong generation = fixture.TryGetProperty("initialGeneration", out JsonElement initial) ? initial.GetUInt64() : 0;
            WatchSession session = new(scope: new PlaybackScope("run-1", generation));
            foreach (JsonElement step in fixture.GetProperty("steps").EnumerateArray())
            {
                actions++;
                LocalState beforeState = session.LocalState;
                PlaybackScope beforeScope = session.Scope;
                string? beforeMedia = session.MediaId;
                IReadOnlyList<WatchEffect> effects = [];
                string? errorCode = null;
                string run = step.TryGetProperty("ownerRunId", out JsonElement runElement) ? runElement.GetString()! : session.Scope.ClientRunId;
                ulong ownerGeneration = step.TryGetProperty("ownerGeneration", out JsonElement gen) ? gen.GetUInt64() : session.Scope.MediaGeneration;
                PlaybackScope owner = new(run, ownerGeneration);
                try
                {
                    switch (step.GetProperty("op").GetString())
                    {
                        case "select": effects = session.Select(step.GetProperty("mediaId").GetString()!); break;
                        case "start": effects = session.Start(); break;
                        case "loaded": session.Loaded(owner); break;
                        case "observe":
                            JsonElement duration = step.GetProperty("durationMs");
                            session.RecordPlayback(owner, step.GetProperty("positionMs").GetInt64(),
                                duration.ValueKind == JsonValueKind.Null ? null : duration.GetInt64(),
                                !step.TryGetProperty("paused", out JsonElement paused) || paused.GetBoolean());
                            break;
                        case "home": session.ReturnToLibrary(); break;
                        case "continue": session.ContinueWatching(); break;
                        case "end": effects = session.End(); break;
                        case "cancel": effects = session.Cancel(owner); break;
                        case "preferences":
                            session.SetPreferences(session.LocalState.Preferences with
                            {
                                MovieVolume = step.GetProperty("movieVolume").GetDouble(),
                                CallVolume = step.GetProperty("callVolume").GetDouble()
                            });
                            break;
                        case "restart": session = new(session.LocalState, new PlaybackScope("run-2", 0)); break;
                        default: throw new InvalidOperationException("Unknown fixture operation");
                    }
                }
                catch (ContractException error) { errorCode = Lower(error.Rejection.ToString()); }
                catch (WatchException error) { errorCode = Lower(error.Rejection.ToString()); }
                string? expectedError = step.TryGetProperty("error", out JsonElement rejection) ? rejection.GetString() : null;
                Require(errorCode == expectedError, $"Rejection in {fixture.GetProperty("name")} / {step.GetProperty("op")}: {errorCode}");
                if (errorCode is not null)
                {
                    Require(EqualState(session.LocalState, beforeState) && session.Scope == beforeScope && session.MediaId == beforeMedia,
                        "Rejected work must not mutate local state or ownership");
                }
                JsonElement expected = step.GetProperty("expected");
                Require(Lower(session.Phase.ToString()) == expected.GetProperty("phase").GetString(), "Unexpected phase");
                Require(session.Scope.MediaGeneration == expected.GetProperty("generation").GetUInt64(), "Unexpected generation");
                Require(session.PositionMs == expected.GetProperty("positionMs").GetInt64(), "Unexpected position");
                Require(session.Paused == expected.GetProperty("paused").GetBoolean(), "Unexpected pause state");
                Require(session.PlayerPresented == expected.GetProperty("playerPresented").GetBoolean(), "Unexpected presentation state");
                Require(effects.Select(Describe).SequenceEqual(expected.GetProperty("effects").EnumerateArray().Select(item => item.GetString()!)),
                    "Unexpected local resource effects");
            }
        }
        Require(actions == 54, "Every lifecycle action must execute");
    }

    private static void Persistence(string directory)
    {
        string path = Path.Combine(directory, "nested", "state.json");
        FileLocalStateStore store = new(path);
        WatchSession session = new();
        session.Select("movie-a"); session.Start(); session.Loaded(session.Scope);
        session.RecordPlayback(session.Scope, 12345, 50000, paused: true);
        LocalPreferences preferences = LocalPreferences.CreateDefault() with { MovieVolume = .25, CallVolume = 0, CameraEnabled = false };
        session.SetPreferences(preferences);
        store.Write(session.LocalState);
        byte[] data = File.ReadAllBytes(path);
        LocalStateRead loaded = store.Read();
        Require(loaded.Status == LocalStateStatus.Loaded, "Saved state must reload");
        WatchSession restarted = new(loaded.State!);
        Require(restarted.Scope.ClientRunId != session.Scope.ClientRunId && restarted.Phase == WatchPhase.Selected
            && !restarted.PlayerPresented && restarted.Paused && restarted.PositionMs == 12345
            && restarted.LocalState.Preferences == preferences, "Restart must restore preferences and position without playback");
        ExpectError(() => store.Write(loaded.State! with { Preferences = preferences with { MovieVolume = double.NaN } }));
        Require(File.ReadAllBytes(path).SequenceEqual(data), "An invalid write must preserve existing bytes");
        Require(Directory.GetFiles(Path.GetDirectoryName(path)!).Length == 1, "Successful writes must leave no temporary files");
        string occupied = Path.Combine(directory, "occupied");
        Directory.CreateDirectory(occupied);
        string sentinel = Path.Combine(occupied, "keep");
        File.WriteAllText(sentinel, "unchanged");
        ExpectError(() => new FileLocalStateStore(occupied).Write(loaded.State!));
        Require(File.ReadAllText(sentinel) == "unchanged", "An OS failure must preserve the destination");
        foreach (byte[] corrupt in new[] { "{"u8.ToArray(), new byte[FileLocalStateStore.MaximumBytes + 1] })
        {
            File.WriteAllBytes(path, corrupt);
            Require(store.Read().Status == LocalStateStatus.Invalid && File.ReadAllBytes(path).SequenceEqual(corrupt), "Corrupt state must be recoverable without modifying it");
        }
        byte[] future = "{\"version\":2,\"futureSetting\":true}"u8.ToArray();
        File.WriteAllBytes(path, future);
        Require(store.Read().Status == LocalStateStatus.UnsupportedVersion, "Future state must remain identifiable");
        try
        {
            store.Write(LocalState.CreateDefault());
            throw new InvalidOperationException("A future state format must reject writes");
        }
        catch (WatchException error) when (error.Rejection == WatchRejection.UnsupportedVersion) { }
        Require(File.ReadAllBytes(path).SequenceEqual(future), "Older clients must not overwrite a future format");
    }

    private static void ResumeHistory()
    {
        WatchSession session = new();
        for (int index = 0; index <= 256; index++)
        {
            session.Select($"movie-{index}"); session.Start(); session.Loaded(session.Scope);
            session.RecordPlayback(session.Scope, index + 1, null, paused: true);
        }
        Require(session.LocalState.ResumePositions.Length == 256 && session.LocalState.ResumePositionFor("movie-0") == 0
            && session.LocalState.ResumePositionFor("movie-256") == 257, "History must evict the least recently updated entry");
        session.RecordPlayback(session.Scope, 500, null, paused: true);
        Require(session.LocalState.ResumePositions.Length == 256 && session.LocalState.ResumePositions[^1].PositionMs == 500,
            "A repeated observation must update rather than duplicate a resume entry");
        session.Select("movie-1"); session.Start(); session.Loaded(session.Scope);
        session.RecordPlayback(session.Scope, 900, null, paused: true);
        session.Select("movie-257"); session.Start(); session.Loaded(session.Scope);
        session.RecordPlayback(session.Scope, 1, null, paused: true);
        Require(session.LocalState.ResumePositionFor("movie-1") == 900 && session.LocalState.ResumePositionFor("movie-2") == 0,
            "A recently updated old movie must survive eviction");
        ExpectError(() => (session.LocalState with
        {
            ResumePositions = session.LocalState.ResumePositions.Add(new ResumePosition { MediaId = "extra", PositionMs = 1 })
        }).Validate());
    }

    private static string Describe(WatchEffect effect) => effect switch
    {
        WatchEffect.Load load => $"load:{load.Request.Scope.ClientRunId}:{load.Request.Scope.MediaGeneration}:{load.Request.MediaId}:{load.Request.PositionMs}",
        WatchEffect.Release release => $"release:{release.Scope.ClientRunId}:{release.Scope.MediaGeneration}",
        _ => throw new InvalidOperationException("Unknown resource effect")
    };

    private static bool EqualState(LocalState left, LocalState right) => left.Version == right.Version
        && left.Preferences == right.Preferences && left.SelectedMediaId == right.SelectedMediaId
        && left.ResumePositions.SequenceEqual(right.ResumePositions);

    private static string Lower(string value) => char.ToLowerInvariant(value[0]) + value[1..];

    private static void ExpectError(Action action)
    {
        try { action(); }
        catch (Exception error) when (error is WatchException or ContractException or IOException or UnauthorizedAccessException) { return; }
        throw new InvalidOperationException("Expected operation to fail");
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) { throw new InvalidOperationException(message); }
    }
}
