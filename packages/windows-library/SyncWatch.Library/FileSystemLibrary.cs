using System.Security.Cryptography;
using System.Text;

namespace SyncWatch.Library;

/// <summary>Local filesystem facts; paths and timestamps never form a peer descriptor.</summary>
public sealed record LocalMediaFile(string Id, string Title, string RelativePath, string File,
    long SizeBytes, DateTimeOffset ModificationDate);

/// <summary>The caller retains the selected folder grant. Publish only completed snapshots.</summary>
public sealed class FileSystemLibrary
{
    private static readonly HashSet<string> Extensions = new(StringComparer.OrdinalIgnoreCase)
        { ".mkv", ".mp4", ".avi", ".mov", ".m4v", ".webm", ".wmv", ".mpg", ".mpeg", ".ts", ".m2ts" };

    public Task<IReadOnlyList<LocalMediaFile>> ScanAsync(string root, string rootId, bool recursive, CancellationToken cancellation = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(root);
        if (!Guid.TryParseExact(rootId, "D", out var id) || id.ToString("D") != rootId) throw new ArgumentException("library-root-id", nameof(rootId));
        if (!Path.IsPathFullyQualified(root)) throw new ArgumentException("absolute-library-root", nameof(root));
        return Task.Run<IReadOnlyList<LocalMediaFile>>(() => Scan(Path.GetFullPath(root), rootId, recursive, cancellation), cancellation);
    }

    private static IReadOnlyList<LocalMediaFile> Scan(string root, string rootId, bool recursive, CancellationToken cancellation)
    {
        if ((System.IO.File.GetAttributes(root) & FileAttributes.Directory) == 0) throw new IOException("library-root");
        var pending = new Stack<(string Path, string Relative)>();
        pending.Push((root, ""));
        var files = new List<LocalMediaFile>();
        while (pending.TryPop(out var directory))
        {
            cancellation.ThrowIfCancellationRequested();
            foreach (string path in Directory.EnumerateFileSystemEntries(directory.Path))
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
                if (dot < 0 || !Extensions.Contains(filename[dot..])) continue;
                var info = new FileInfo(path);
                string id = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(rootId + "\0" + relative)));
                files.Add(new(id, filename, relative, path, info.Length, info.LastWriteTimeUtc));
            }
        }
        cancellation.ThrowIfCancellationRequested();
        files.Sort((a, b) => Encoding.UTF8.GetBytes(a.RelativePath).AsSpan().SequenceCompareTo(Encoding.UTF8.GetBytes(b.RelativePath)));
        return files.AsReadOnly();
    }
}
