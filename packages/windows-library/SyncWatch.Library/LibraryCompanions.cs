namespace SyncWatch.Library;

public enum LibraryCompanionKind { Audio, Subtitles }

/// <summary>A local scan version; never a room descriptor or persisted native track ID.</summary>
public sealed record LocalCompanionFile(string Id, LibraryCompanionKind Kind, string RelativePath,
    string File, long SizeBytes, DateTimeOffset ModificationDate)
{
    public LocalFileAccess Open()
    {
        var access = LocalFileAccess.Selected(File);
        var facts = new FileInfo(File);
        if (facts.Length != SizeBytes || facts.LastWriteTimeUtc != ModificationDate.UtcDateTime)
            throw new IOException("companion-changed");
        return access;
    }
}
