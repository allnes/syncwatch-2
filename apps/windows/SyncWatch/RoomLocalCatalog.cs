using SyncWatch.Domain;
using SyncWatch.Library;

namespace SyncWatch;

/// <summary>Local file identifiers never become room identifiers. One map lives for one membership.</summary>
internal sealed class RoomLocalCatalog
{
    internal sealed record Publication(IReadOnlyList<MediaDescriptor> Items, IReadOnlyDictionary<string, string> LocalIds);
    private IReadOnlyDictionary<string, string> acknowledged = new Dictionary<string, string>();
    private IReadOnlyDictionary<string, string> pending = new Dictionary<string, string>();
    internal Publication Prepare(IReadOnlyList<LocalMediaFile> files, MediaDescriptor? prepared = null)
    {
        int extra = prepared is not null && !files.Any(p => p.Id == prepared.MediaId) ? 1 : 0;
        if (files.Count + extra > 2048 || prepared is not null && (prepared.FullHashSha256 is null || prepared.DurationMs is not > 0)) throw new InvalidOperationException("catalog-limit");
        Dictionary<string, string> next = new(StringComparer.Ordinal); List<MediaDescriptor> items = [];
        void Add(string localId, string title, long size, long? duration, string? hash)
        {
            string id = acknowledged.GetValueOrDefault(localId) ?? pending.GetValueOrDefault(localId) ?? "media-" + Guid.NewGuid().ToString("N");
            if (!next.TryAdd(localId, id)) throw new InvalidOperationException("catalog-duplicate");
            items.Add(new(id, title, MediaDescriptor.NormalizedTitleKey(title), size, duration, hash));
        }
        foreach (var file in files)
        {
            if (prepared is not null && file.Id == prepared.MediaId) Add(file.Id, prepared.Title, prepared.FileSizeBytes, prepared.DurationMs, prepared.FullHashSha256);
            else Add(file.Id, MediaDescriptor.LogicalTitle(file.Title), file.SizeBytes, null, null);
        }
        if (prepared is not null && !next.ContainsKey(prepared.MediaId)) Add(prepared.MediaId, prepared.Title, prepared.FileSizeBytes, prepared.DurationMs, prepared.FullHashSha256);
        pending = next;
        return new(items.AsReadOnly(), new System.Collections.ObjectModel.ReadOnlyDictionary<string, string>(next));
    }
    internal void Acknowledge(Publication publication) => acknowledged = publication.LocalIds;
    internal string? LocalId(string roomId) => acknowledged.FirstOrDefault(p => p.Value == roomId).Key;
}
