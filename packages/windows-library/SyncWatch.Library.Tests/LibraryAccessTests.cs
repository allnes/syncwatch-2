using System.Text;
using System.Text.Json;
using SyncWatch.Library;

internal static class LibraryAccessTests
{
    internal static void Run(string fixture, string scratch)
    {
        string selected = Path.Combine(scratch, "selected"); Directory.CreateDirectory(selected);
        var access = LibraryFolderAccess.Selected(selected);
        var record = access.Record;
        string path = Path.Combine(scratch, "state", "library-access.json");
        var store = new FileLibraryAccessStore(path);
        Require(store.Read().Status == LibraryAccessStatus.Missing, "missing-store");
        store.Write(record);
        Require(store.Read() == new LibraryAccessRead(LibraryAccessStatus.Loaded, record), "round-trip");
        var changed = record with { AutoRefresh = false, ScanSubfolders = false };
        store.Write(changed); Require(store.Read().Record == changed, "replace-record");
        string valid = File.ReadAllText(path);
        foreach (string replacement in new[] { "1.0", "1e0" })
        {
            File.WriteAllText(path, valid.Replace("\"version\":1", "\"version\":" + replacement, StringComparison.Ordinal));
            Require(store.Read().Status == LibraryAccessStatus.Invalid, "integer-version");
        }
        using var corpus = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(Path.GetDirectoryName(fixture)!, "library-access.json")));
        foreach (var entry in corpus.RootElement.GetProperty("cases").EnumerateArray())
        {
            byte[] bytes = Encoding.UTF8.GetBytes(entry.GetProperty("text").GetString()!); File.WriteAllBytes(path, bytes);
            var expected = Enum.Parse<LibraryAccessStatus>(entry.GetProperty("status").GetString()!, true);
            Require(store.Read().Status == expected, entry.GetProperty("name").GetString()!);
            if (expected == LibraryAccessStatus.UnsupportedVersion)
            {
                try { store.Write(record); throw new Exception("future-overwritten"); } catch (InvalidOperationException) { }
                Require(File.ReadAllBytes(path).SequenceEqual(bytes), "future-preserved");
            }
        }
        File.WriteAllBytes(path, new byte[FileLibraryAccessStore.MaximumBytes + 1]);
        Require(store.Read().Status == LibraryAccessStatus.Invalid, "oversize");
        File.WriteAllBytes(path, [255]); Require(store.Read().Status == LibraryAccessStatus.Invalid, "utf8");
        store.Write(record);
        Require(LibraryFolderAccess.Restore(store.Read().Record!).RootId == record.RootId, "restore-root");
        Directory.Delete(selected);
        try { LibraryFolderAccess.Restore(record); throw new Exception("missing-root-restored"); }
        catch (IOException error) when (error is FileNotFoundException or DirectoryNotFoundException) { }
        try { new FileLibraryAccessStore(scratch).Read(); throw new Exception("directory-file-read"); }
        catch (UnauthorizedAccessException) { }
        catch (IOException) { }
        Console.WriteLine("SYNCWATCH_LIBRARY_ACCESS_OK");
    }
    private static void Require(bool value, string name) { if (!value) throw new InvalidOperationException(name); }
}
