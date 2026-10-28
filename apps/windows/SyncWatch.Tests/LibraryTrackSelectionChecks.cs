using SyncWatch;
using SyncWatch.Design;
using SyncWatch.Domain;
using SyncWatch.Library;

internal static class LibraryTrackSelectionChecks
{
    private static void Require(bool value) { if (!value) throw new InvalidOperationException("library track draft"); }
    private static void Reject(Action action)
    {
        bool rejected = false;
        try { action(); } catch (InvalidOperationException) { rejected = true; }
        Require(rejected);
    }
    internal static void Run()
    {
        var metadata = new MediaMetadata(1000, 1, 1, 2, 2, ["First", "Second"], ["English", "Русский"]);
        var model = new LibraryTrackSelection().Reset(metadata);
        Require(model.AudioName == "First" && model.SubtitlesDisabled && model.SubtitleName is null);
        model = model.Open("audio", "en"); var audio = model.Menu!; SelectionMenuRequest? request = null;
        audio.Dispatch("1", audio.ContextToken, value => request = value);
        var old = request!; model = model.Select(old); var captured = model.Preferences;
        Require(model.AudioName == "Second" && model.Menu is null);
        PlaybackTrack[] native = [new(-1, "Disable"), new(101, "First"), new(299, "Second")];
        Require(captured.Resolve(native, false) == 299);
        Reject(() => captured.Resolve(native.Reverse().ToArray(), false));
        Reject(() => captured.Resolve([new(1, "Other")], false));
        model = model.Open("subtitles", "ru"); var subtitles = model.Menu!;
        model = model.Select(old); Require(model.Menu?.ContextToken == subtitles.ContextToken && model.SubtitlesDisabled);
        subtitles.Dispatch("1", subtitles.ContextToken, value => model = model.Select(value));
        Require(model.SubtitleName == "Русский" && !model.SubtitlesDisabled && captured.SubtitleIndex is null);
        model = model.Reset(metadata).Select(old);
        Require(model.AudioName == "First" && model.SubtitlesDisabled && model.Menu is null);
        model = model.Reset().Open("audio", "en");
        Require(model.Menu is null && model.AudioName is null && !model.SubtitlesDisabled);
        Console.WriteLine("SYNCWATCH_LIBRARY_TRACK_DRAFT_OK fresh IDs, reordered/changed input, stale menu, immutable Start");
    }
}
