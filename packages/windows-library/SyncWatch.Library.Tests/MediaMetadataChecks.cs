using SyncWatch.Library;

internal static class MediaMetadataChecks
{
    public static void Run()
    {
        var names = new List<string> { "English", "Русский" };
        var value = new MediaMetadata(1000, 320, 180, 2, 0, names, []);
        names[0] = "Changed";
        Require(value.AudioTrackNames!.SequenceEqual(new[] { "English", "Русский" }) && value.SubtitleTrackNames!.Count == 0);
        var equal = new MediaMetadata(1000, 320, 180, 2, 0, ["English", "Русский"], []);
        Require(value == equal && value.GetHashCode() == equal.GetHashCode());
        Require(new MediaMetadata(null, 0, 0, 2, 0).AudioTrackNames is null);
        foreach (string[] invalid in new[] { Array.Empty<string>(), ["English", "Русский"], ["bad\0label"], [new string('é', 2049)] })
        {
            try { _ = new MediaMetadata(null, 0, 0, 1, 0, invalid, []); throw new InvalidOperationException("invalid-names-accepted"); }
            catch (ArgumentException) { }
        }
        try { _ = new MediaMetadata(null, 0, 0, 0, 1, [], []); throw new InvalidOperationException("subtitle-count-accepted"); }
        catch (ArgumentException) { }
        Require(new MediaMetadata(null, 0, 0, 1, 0, [new string('é', 2048)], []).AudioTrackNames!.Single().Length == 2048);
        try { ((IList<string>)value.AudioTrackNames!)[0] = "Changed"; throw new InvalidOperationException("mutable-names"); }
        catch (NotSupportedException) { }
    }
    private static void Require(bool condition) { if (!condition) throw new InvalidOperationException("metadata-names"); }
}
