using System.Text;
using System.Text.Json;

namespace SyncWatch.Library;

public sealed record LibraryAccessRecord(string RootId, string RootPath, bool ScanSubfolders = true, bool AutoRefresh = true)
{
    public int Version { get; init; } = 1;
    public string Platform { get; init; } = "windows";
    public string? Bookmark { get; init; }
    public void Validate()
    {
        if (Version != 1 || Platform != "windows" || Bookmark is not null
            || !Guid.TryParseExact(RootId, "D", out var id) || id.ToString("D") != RootId
            || !Path.IsPathFullyQualified(RootPath) || RootPath.Contains('\0')) throw new InvalidDataException("library-access-record");
    }
}
public enum LibraryAccessStatus { Missing, Loaded, Invalid, UnsupportedVersion }
public sealed record LibraryAccessRead(LibraryAccessStatus Status, LibraryAccessRecord? Record = null);

/// <summary>The caller chooses an application-owned path and serializes calls outside rendering.</summary>
public interface ILibraryAccessStore
{
    LibraryAccessRead Read();
    void Write(LibraryAccessRecord record);
}

public sealed class FileLibraryAccessStore(string path) : ILibraryAccessStore
{
    public const int MaximumBytes = 262144;
    private static readonly JsonSerializerOptions Options = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
    private static readonly HashSet<string> Keys = ["version", "platform", "rootId", "rootPath", "bookmark", "scanSubfolders", "autoRefresh"];
    private readonly string path = Path.GetFullPath(path);
    public LibraryAccessRead Read()
    {
        byte[] buffer = new byte[MaximumBytes + 1];
        int count;
        try { using var stream = File.OpenRead(path); count = stream.ReadAtLeast(buffer, buffer.Length, false); }
        catch (FileNotFoundException) { return new(LibraryAccessStatus.Missing); }
        catch (DirectoryNotFoundException) { return new(LibraryAccessStatus.Missing); }
        if (count > MaximumBytes) return new(LibraryAccessStatus.Invalid);
        try
        {
            _ = new UTF8Encoding(false, true).GetCharCount(buffer, 0, count);
            using var document = JsonDocument.Parse(buffer.AsMemory(0, count));
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object) return new(LibraryAccessStatus.Invalid);
            var names = root.EnumerateObject().Select(x => x.Name).ToArray();
            if (names.Distinct(StringComparer.Ordinal).Count() != names.Length
                || !root.TryGetProperty("version", out var version) || version.ValueKind != JsonValueKind.Number
                || !version.TryGetInt32(out int value) || value < 0) return new(LibraryAccessStatus.Invalid);
            if (value != 1) return new(LibraryAccessStatus.UnsupportedVersion);
            if (!Keys.SetEquals(names)) return new(LibraryAccessStatus.Invalid);
            var record = root.Deserialize<LibraryAccessRecord>(Options) ?? throw new InvalidDataException();
            record.Validate(); return new(LibraryAccessStatus.Loaded, record);
        }
        catch (InvalidOperationException) { return new(LibraryAccessStatus.Invalid); }
        catch (JsonException) { return new(LibraryAccessStatus.Invalid); }
        catch (InvalidDataException) { return new(LibraryAccessStatus.Invalid); }
        catch (ArgumentException) { return new(LibraryAccessStatus.Invalid); }
    }
    public void Write(LibraryAccessRecord record)
    {
        record.Validate();
        if (Read().Status == LibraryAccessStatus.UnsupportedVersion) throw new InvalidOperationException("unsupported-library-version");
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(record, Options);
        if (bytes.Length > MaximumBytes) throw new InvalidDataException("library-access-record");
        string parent = Path.GetDirectoryName(path)!; Directory.CreateDirectory(parent);
        string temporary = Path.Combine(parent, ".library-access-" + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { stream.Write(bytes); stream.Flush(true); }
            File.Move(temporary, path, true);
        }
        finally { File.Delete(temporary); }
    }
}
