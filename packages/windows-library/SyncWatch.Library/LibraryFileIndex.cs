using System.Text;

namespace SyncWatch.Library;

/// <summary>Relationships in one completed authorized listing; paths stay local and root-relative.</summary>
public sealed class LibraryFileIndex
{
    private readonly bool caseSensitive;
    private readonly HashSet<string> videos;
    private readonly Dictionary<string, int> videoCounts = [];
    private readonly HashSet<string> extraDirectories = [];
    private readonly Dictionary<string, IReadOnlyList<string>> audio;
    private readonly Dictionary<string, IReadOnlyList<string>> subtitles;

    public LibraryFileIndex(IEnumerable<string> videos, IEnumerable<string> audio, IEnumerable<string> subtitles, bool caseSensitive)
    {
        this.caseSensitive = caseSensitive;
        string[] movies = videos.ToArray(), audioFiles = audio.ToArray(), subtitleFiles = subtitles.ToArray();
        this.videos = movies.ToHashSet();
        foreach (string path in movies.Concat(audioFiles).Concat(subtitleFiles))
            if (string.IsNullOrEmpty(path) || path.StartsWith('/') || path.Contains('\0') ||
                path.Split('/').Any(part => part.Length == 0 || part is "." or ".."))
                throw new ArgumentException("library-relative-path");
        foreach (string movie in movies)
        {
            string directory = Directory(movie);
            videoCounts[directory] = videoCounts.GetValueOrDefault(directory) + 1;
        }
        foreach (string path in audioFiles.Concat(subtitleFiles))
        {
            string directory = Directory(path);
            extraDirectories.Add(directory);
            if (directory.Length != 0) extraDirectories.Add(Directory(directory));
        }
        var stems = movies.Select(Stem).ToHashSet();
        this.audio = Index(audioFiles, stems);
        this.subtitles = Index(subtitleFiles, stems);
    }
    public bool IsFolderMovie(string video)
    {
        if (!videos.Contains(video)) return false;
        string directory = Directory(video);
        return videoCounts.GetValueOrDefault(directory) == 1 && extraDirectories.Contains(directory);
    }
    public IReadOnlyList<string> AudioPaths(string video) => videos.Contains(video) ? audio.GetValueOrDefault(Stem(video)) ?? [] : [];
    public IReadOnlyList<string> SubtitlePaths(string video) => videos.Contains(video) ? subtitles.GetValueOrDefault(Stem(video)) ?? [] : [];
    private Dictionary<string, IReadOnlyList<string>> Index(string[] paths, HashSet<string> stems)
    {
        var result = new Dictionary<string, List<string>>();
        Array.Sort(paths, (a, b) =>
        {
            int order = Compare(Name(a), Name(b));
            return order != 0 ? order : Compare(a, b);
        });
        foreach (string path in paths)
        {
            string name = Name(path);
            for (int dot = name.IndexOf('.'); dot >= 0; dot = name.IndexOf('.', dot + 1))
            {
                string prefix = Key(name[..dot]);
                if (!stems.Contains(prefix)) continue;
                if (!result.TryGetValue(prefix, out var matches)) result.Add(prefix, matches = []);
                matches.Add(path);
            }
        }
        return result.ToDictionary(item => item.Key, item => (IReadOnlyList<string>)item.Value.AsReadOnly());
    }
    private string Key(string value) => caseSensitive ? value : value.ToLowerInvariant();
    private string Stem(string path) { string name = Name(path); int dot = name.LastIndexOf('.'); return Key(dot < 0 ? name : name[..dot]); }
    private static string Name(string path) => path[(path.LastIndexOf('/') + 1)..];
    private static string Directory(string path) { int slash = path.LastIndexOf('/'); return slash < 0 ? "" : path[..slash]; }
    private static int Compare(string a, string b) => Encoding.UTF8.GetBytes(a).AsSpan().SequenceCompareTo(Encoding.UTF8.GetBytes(b));
}
