using SyncWatch.Domain;
using SyncWatch.Library;

namespace SyncWatch;

/// <summary>Local file identifiers never become room identifiers. One map lives for one membership.</summary>
internal sealed class RoomLocalCatalog
{
    internal sealed record Publication(IReadOnlyList<MediaDescriptor> Items, IReadOnlyDictionary<string, string> LocalIds);
    private IReadOnlyDictionary<string, string> acknowledged = new Dictionary<string, string>();
    private IReadOnlyDictionary<string, string> pending = new Dictionary<string, string>();
    internal Publication Prepare(IReadOnlyList<LocalMediaFile> files)
    {
        if (files.Count > 2048) throw new InvalidOperationException("catalog-limit");
        Dictionary<string, string> next = new(StringComparer.Ordinal); List<MediaDescriptor> items = [];
        foreach (var file in files)
        {
            string id = acknowledged.GetValueOrDefault(file.Id) ?? pending.GetValueOrDefault(file.Id) ?? "media-" + Guid.NewGuid().ToString("N");
            if (!next.TryAdd(file.Id, id)) throw new InvalidOperationException("catalog-duplicate");
            string title = MediaDescriptor.LogicalTitle(file.Title);
            items.Add(new(id, title, MediaDescriptor.NormalizedTitleKey(title), file.SizeBytes, null, null));
        }
        pending = next;
        return new(items.AsReadOnly(), new System.Collections.ObjectModel.ReadOnlyDictionary<string, string>(next));
    }
    internal void Acknowledge(Publication publication) => acknowledged = publication.LocalIds;
    internal string? LocalId(string roomId) => acknowledged.FirstOrDefault(p => p.Value == roomId).Key;
}
