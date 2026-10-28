namespace SyncWatch.Library;

/// <summary>A transient explicitly selected local file; native playback owns its eventual read lease.</summary>
public sealed class LocalFileAccess
{
    public string File { get; }
    private LocalFileAccess(string file) { File = file; }
    public static LocalFileAccess Selected(string file)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(file);
        if (!Path.IsPathFullyQualified(file) || file.StartsWith("\\\\", StringComparison.Ordinal))
            throw new IOException("local-file");
        string path = Path.GetFullPath(file);
        if (!System.IO.File.Exists(path) || (System.IO.File.GetAttributes(path) & (FileAttributes.Directory | FileAttributes.ReparsePoint)) != 0)
            throw new IOException("local-file");
        return new(path);
    }
}
