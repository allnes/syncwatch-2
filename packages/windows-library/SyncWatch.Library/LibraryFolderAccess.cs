namespace SyncWatch.Library;

/// <summary>Local selected-folder ownership. Restoring metadata rechecks current OS access.</summary>
public sealed class LibraryFolderAccess
{
    public LibraryAccessRecord Record { get; }
    public string RootId => Record.RootId;
    public string RootPath => Record.RootPath;
    private LibraryFolderAccess(LibraryAccessRecord record)
    {
        record.Validate();
        if ((File.GetAttributes(record.RootPath) & FileAttributes.Directory) == 0) throw new IOException("library-root");
        Record = record;
    }
    public static LibraryFolderAccess Selected(string path, bool scanSubfolders = true, bool autoRefresh = true)
    {
        if (!Path.IsPathFullyQualified(path)) throw new ArgumentException("absolute-library-root", nameof(path));
        return new(new(Guid.NewGuid().ToString("D"), Path.GetFullPath(path), scanSubfolders, autoRefresh));
    }
    public static LibraryFolderAccess Restore(LibraryAccessRecord record) => new(record);
}
