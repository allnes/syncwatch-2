using System.Text.Json;
using SyncWatch.Library;

internal static class LibraryCompanionScanChecks
{
    public static async Task RunAsync(string fixture)
    {
        using var corpus = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(Path.GetDirectoryName(fixture)!, "library-companion-scan.json")));
        var data = corpus.RootElement;
        string root = Path.Combine(Path.GetTempPath(), "syncwatch-companions-" + Guid.NewGuid());
        Directory.CreateDirectory(root);
        try
        {
            foreach (string name in Strings(data.GetProperty("files")))
            {
                string path = Path.Combine(root, name.Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(Path.GetDirectoryName(path)!); File.WriteAllText(path, name);
            }
            try { File.CreateSymbolicLink(Path.Combine(root, "Movie.Part.1.link.srt"), Path.Combine(root, "Movie.Part.1.en.srt")); }
            catch (UnauthorizedAccessException) { Console.WriteLine("SKIP: companion symlink creation privilege unavailable"); }
            var scanner = new FileSystemLibrary(new Dictionary<string, LibraryCompanionKind> { ["srt"] = LibraryCompanionKind.Subtitles, ["wav"] = LibraryCompanionKind.Audio });
            string id = data.GetProperty("rootId").GetString()!;
            var files = await scanner.ScanAsync(root, id, true);
            bool insensitive = File.Exists(Path.Combine(root, "mOvIe.PaRt.1.mkv"));
            foreach (var file in files)
            {
                var expected = data.GetProperty("expected").TryGetProperty(file.RelativePath, out var paths) ? Strings(paths).ToList() : [];
                if (insensitive && file.Title == "Movie.Part.1.mkv") expected.Add(data.GetProperty("insensitiveExtra").GetString()!);
                Require(file.Companions.Select(f => f.RelativePath).SequenceEqual(expected), file.RelativePath);
                if (Strings(data.GetProperty("folderMovies")).Contains(file.RelativePath)) Require(file.FolderMovie, file.RelativePath);
                if (Strings(data.GetProperty("notFolderMovies")).Contains(file.RelativePath)) Require(!file.FolderMovie, file.RelativePath);
                Require(file.Companions.All(f => f.Id != file.Id && f.SizeBytes > 0), "local-facts");
            }
            var movie = files.Single(f => f.RelativePath == "Movie.Part.1.mkv");
            var durations = new LibraryDurationCache(); durations.Record(1000, movie);
            var subtitle = movie.Companions.First(f => f.Kind == LibraryCompanionKind.Subtitles);
            Require(subtitle.Open().File == subtitle.File, "open-current");
            File.WriteAllText(subtitle.File, "changed"); Reject(subtitle);
            var updated = await scanner.ScanAsync(root, id, true);
            durations.Reconcile(updated);
            Require(durations.Duration(updated.Single(f => f.Id == movie.Id)) == 1000, "companion-independent-duration");
            var next = updated.Single(f => f.Id == movie.Id).Companions.Single(f => f.Id == subtitle.Id);
            Require(next.SizeBytes == 7 && next != subtitle, "rescan-version");
            File.Delete(next.File); Reject(next);
            var flat = await scanner.ScanAsync(root, id, false);
            Require(flat.Count == 1 && flat[0].Companions.Count == 0 && !flat[0].FolderMovie, "flat-scan");
        }
        finally { Directory.Delete(root, true); Require(!Directory.Exists(root), "cleanup"); }
    }
    private static IEnumerable<string> Strings(JsonElement value) => value.EnumerateArray().Select(x => x.GetString()!);
    private static void Require(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
    private static void Reject(LocalCompanionFile file)
    {
        try { _ = file.Open(); throw new InvalidOperationException("stale-companion-accepted"); }
        catch (IOException) { }
    }
}
