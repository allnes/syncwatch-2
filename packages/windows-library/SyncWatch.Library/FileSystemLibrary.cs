using System.Security.Cryptography;
using System.Text;

namespace SyncWatch.Library;

/// <summary>Local filesystem facts; paths and timestamps never form a peer descriptor.</summary>
public sealed record LocalMediaFile(string Id, string Title, string RelativePath, string File,
    long SizeBytes, DateTimeOffset ModificationDate)
{
    public IReadOnlyList<LocalCompanionFile> Companions { get; init; } = Array.Empty<LocalCompanionFile>();
    public bool FolderMovie { get; init; }
}

/// <summary>The caller retains the selected folder grant. Publish only completed snapshots.</summary>
public sealed class FileSystemLibrary
{
    private readonly IReadOnlyDictionary<string, LibraryCompanionKind> companionExtensions;
    public FileSystemLibrary(IReadOnlyDictionary<string, LibraryCompanionKind>? companionExtensions = null)
    {
        this.companionExtensions = companionExtensions is null ? new Dictionary<string, LibraryCompanionKind>()
            : new Dictionary<string, LibraryCompanionKind>(companionExtensions, StringComparer.OrdinalIgnoreCase);
    }
    private static readonly HashSet<string> Extensions = new(StringComparer.OrdinalIgnoreCase)
        { ".mkv", ".mp4", ".avi", ".mov", ".m4v", ".webm", ".wmv", ".mpg", ".mpeg", ".ts", ".m2ts" };

    public Task<IReadOnlyList<LocalMediaFile>> ScanAsync(string root, string rootId, bool recursive, CancellationToken cancellation = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(root);
        if (!Guid.TryParseExact(rootId, "D", out var id) || id.ToString("D") != rootId) throw new ArgumentException("library-root-id", nameof(rootId));
        if (!Path.IsPathFullyQualified(root)) throw new ArgumentException("absolute-library-root", nameof(root));
        return Task.Run<IReadOnlyList<LocalMediaFile>>(() => Scan(Path.GetFullPath(root), rootId, recursive, cancellation), cancellation);
    }

    private IReadOnlyList<LocalMediaFile> Scan(string root, string rootId, bool recursive, CancellationToken cancellation)
    {
        if ((System.IO.File.GetAttributes(root) & FileAttributes.Directory) == 0) throw new IOException("library-root");
        var pending = new Stack<(string Path, string Relative)>();
        pending.Push((root, ""));
        var files = new List<LocalMediaFile>();
        var companions = new List<LocalCompanionFile>();
        var caseSensitive = new Dictionary<string, bool>(StringComparer.Ordinal);
        while (pending.TryPop(out var directory))
        {
            cancellation.ThrowIfCancellationRequested();
            string[] children = Directory.GetFileSystemEntries(directory.Path);
            var names = children.Select(Path.GetFileName).ToHashSet(StringComparer.Ordinal);
            foreach (string path in children)
            {
                cancellation.ThrowIfCancellationRequested();
                FileAttributes attributes = System.IO.File.GetAttributes(path);
                if ((attributes & FileAttributes.ReparsePoint) != 0) continue;
                string relative = directory.Relative + Path.GetFileName(path);
                if ((attributes & FileAttributes.Directory) != 0)
                {
                    if (recursive) pending.Push((path, relative + "/"));
                    continue;
                }
                string filename = Path.GetFileName(path);
                int dot = filename.LastIndexOf('.');
                if (dot < 0) continue;
                string extensionName = filename[(dot + 1)..];
                bool video = Extensions.Contains(filename[dot..]);
                bool extra = companionExtensions.TryGetValue(extensionName, out var kind);
                if (!video && !extra) continue;
                var info = new FileInfo(path);
                string id = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(rootId + "\0" + relative)));
                if (!video)
                {
                    companions.Add(new(id, kind, relative, path, info.Length, info.LastWriteTimeUtc));
                    continue;
                }
                if (!caseSensitive.ContainsKey(directory.Relative))
                {
                    // Read-only probe of a known ASCII extension in the actual directory.
                    string alternate = filename[..(dot + 1)] + new string(extensionName.Select(c =>
                        char.IsUpper(c) ? char.ToLowerInvariant(c) : char.ToUpperInvariant(c)).ToArray());
                    caseSensitive[directory.Relative] = names.Contains(alternate) || !System.IO.File.Exists(Path.Combine(directory.Path, alternate));
                }
                files.Add(new(id, filename, relative, path, info.Length, info.LastWriteTimeUtc));
            }
        }
        cancellation.ThrowIfCancellationRequested();
        string[] paths = files.Select(f => f.RelativePath).ToArray();
        string[] audio = companions.Where(f => f.Kind == LibraryCompanionKind.Audio).Select(f => f.RelativePath).ToArray();
        string[] subtitles = companions.Where(f => f.Kind == LibraryCompanionKind.Subtitles).Select(f => f.RelativePath).ToArray();
        var sensitive = new LibraryFileIndex(paths, audio, subtitles, true);
        var insensitive = new LibraryFileIndex(paths, audio, subtitles, false);
        var byPath = companions.ToDictionary(f => f.RelativePath, StringComparer.Ordinal);
        for (int position = 0; position < files.Count; position++)
        {
            cancellation.ThrowIfCancellationRequested();
            var file = files[position]; int slash = file.RelativePath.LastIndexOf('/');
            string directory = slash < 0 ? "" : file.RelativePath[..(slash + 1)];
            var index = caseSensitive[directory] ? sensitive : insensitive;
            var extras = index.AudioPaths(file.RelativePath).Concat(index.SubtitlePaths(file.RelativePath)).Select(p => byPath[p]).ToList().AsReadOnly();
            files[position] = file with { Companions = extras, FolderMovie = index.IsFolderMovie(file.RelativePath) };
        }
        files.Sort((a, b) => Encoding.UTF8.GetBytes(a.RelativePath).AsSpan().SequenceCompareTo(Encoding.UTF8.GetBytes(b.RelativePath)));
        return files.AsReadOnly();
    }
}
