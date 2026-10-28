using System.Text.Json;
using SyncWatch.Library;

internal static class LibraryFileIndexChecks
{
    internal static void Run(string fixture)
    {
        using var corpus = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(Path.GetDirectoryName(fixture)!, "library-companions.json")));
        static string[] Strings(JsonElement value) => value.EnumerateArray().Select(item => item.GetString()!).ToArray();
        foreach (var item in corpus.RootElement.GetProperty("cases").EnumerateArray())
        {
            string[] videos = Strings(item.GetProperty("videos")), audio = Strings(item.GetProperty("audio")), subtitles = Strings(item.GetProperty("subtitles"));
            foreach (bool reverse in new[] { false, true })
            {
                var index = new LibraryFileIndex(reverse ? videos.Reverse() : videos,
                    reverse ? audio.Reverse() : audio, reverse ? subtitles.Reverse() : subtitles,
                    item.GetProperty("caseSensitive").GetBoolean());
                foreach (var expected in item.GetProperty("expected").EnumerateArray())
                {
                    string video = expected.GetProperty("video").GetString()!;
                    Require(index.IsFolderMovie(video) == expected.GetProperty("folder").GetBoolean(), item);
                    Require(index.AudioPaths(video).SequenceEqual(Strings(expected.GetProperty("audio"))), item);
                    Require(index.SubtitlePaths(video).SequenceEqual(Strings(expected.GetProperty("subtitles"))), item);
                }
                string unknown = "not-in-snapshot/" + (videos.FirstOrDefault()?.Split('/').Last() ?? "film.mkv");
                Require(!index.IsFolderMovie(unknown) && index.AudioPaths(unknown).Count == 0 && index.SubtitlePaths(unknown).Count == 0, item);
            }
        }
        foreach (string path in Strings(corpus.RootElement.GetProperty("invalidPaths")))
        {
            try { _ = new LibraryFileIndex([path], [], [], true); throw new InvalidOperationException("invalid-path-accepted"); }
            catch (ArgumentException) { }
        }
    }
    private static void Require(bool value, JsonElement item)
    {
        if (!value) throw new InvalidOperationException("companion-index:" + item.GetProperty("id").GetString());
    }
}
