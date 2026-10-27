using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using SyncWatch.Domain;

namespace SyncWatch.Room;

public sealed record RoomCatalogEntry(string MemberId, MediaDescriptor Media);

/// <summary>A bootstrap and its complete catalog are published together; no partial view escapes.</summary>
public sealed class RoomCatalogView
{
    public RoomBootstrap Bootstrap { get; }
    public IReadOnlyList<RoomCatalogEntry> Items { get; }
    private RoomCatalogView(RoomBootstrap bootstrap, List<RoomCatalogEntry> items)
    { Bootstrap = bootstrap; Items = items.AsReadOnly(); }

    public static async Task<RoomCatalogView> ReadAsync(RoomBootstrap bootstrap,
        Func<string, CancellationToken, Task<byte[]>> fetch, CancellationToken cancellation = default)
    {
        _ = new RoomCatalogPosition(bootstrap.CatalogCursor, bootstrap);
        string cursor = bootstrap.CatalogCursor;
        List<RoomCatalogEntry> items = []; HashSet<(string, string)> seen = [];
        Dictionary<string, int> counts = new(StringComparer.Ordinal);
        while (true)
        {
            cancellation.ThrowIfCancellationRequested();
            var page = RoomCatalogPage.Decode(await fetch(cursor, cancellation), bootstrap, cursor);
            cancellation.ThrowIfCancellationRequested();
            foreach (var item in page.Items)
            {
                counts.TryGetValue(item.MemberId, out int count);
                // The service permits at most 2048 catalog items per member.
                if (!seen.Add((item.MemberId, item.Media.MediaId)) || ++count > 2048) throw RoomWire.Bad();
                counts[item.MemberId] = count;
            }
            items.AddRange(page.Items);
            if (page.NextCursor is not string next) return new(bootstrap, items);
            cursor = next;
        }
    }
}

/// <summary>One bounded page of a bootstrap's stable view, never a partial replacement catalog.</summary>
public sealed class RoomCatalogPage
{
    public string Epoch { get; }
    public long Sequence { get; }
    public IReadOnlyList<RoomCatalogEntry> Items { get; }
    public string? NextCursor { get; }
    private RoomCatalogPage(string epoch, long sequence, List<RoomCatalogEntry> items, string? nextCursor)
    { Epoch = epoch; Sequence = sequence; Items = items.AsReadOnly(); NextCursor = nextCursor; }

    public static RoomCatalogPage Decode(byte[] bytes, RoomBootstrap bootstrap, string cursor)
    {
        var position = new RoomCatalogPosition(cursor, bootstrap);
        using var document = RoomWire.Parse(bytes); var value = document.RootElement;
        RoomWire.Keys(value, "v", "roomEpoch", "sequence", "items", "nextCursor");
        var entries = value.GetProperty("items");
        if (RoomWire.Integer(value, "v", 1) != 1 || RoomWire.String(value, "roomEpoch") != bootstrap.Snapshot.Epoch
            || RoomWire.Integer(value, "sequence") != bootstrap.Snapshot.Sequence || entries.ValueKind != JsonValueKind.Array
            || entries.GetArrayLength() > 100) throw RoomWire.Bad();
        var members = bootstrap.Snapshot.Members.Select(p => p.MemberId).ToHashSet(StringComparer.Ordinal);
        HashSet<(string, string)> seen = []; List<RoomCatalogEntry> items = [];
        foreach (var entry in entries.EnumerateArray())
        {
            RoomWire.Keys(entry, "memberId", "media");
            string member = RoomWire.String(entry, "memberId");
            if (!members.Contains(member)) throw RoomWire.Bad();
            var descriptor = RoomMedia.Decode(entry.GetProperty("media"));
            if (!seen.Add((member, descriptor.MediaId))) throw RoomWire.Bad();
            items.Add(new(member, descriptor));
        }
        string? next = RoomWire.OptionalString(value.GetProperty("nextCursor"));
        if (next is not null && (items.Count == 0 || new RoomCatalogPosition(next, bootstrap).Offset != position.Offset + items.Count)) throw RoomWire.Bad();
        return new(bootstrap.Snapshot.Epoch, bootstrap.Snapshot.Sequence, items, next);
    }
}

internal sealed class RoomCatalogPosition
{
    public long Offset { get; }
    internal RoomCatalogPosition(string cursor, RoomBootstrap bootstrap)
    {
        static (string View, long Offset) Parse(string value)
        {
            string[] parts = value.Split(':');
            if (parts.Length != 2 || !Regex.IsMatch(parts[1], "\\A(0|[1-9][0-9]{0,15})\\z", RegexOptions.CultureInvariant)
                || !long.TryParse(parts[1], NumberStyles.None, CultureInfo.InvariantCulture, out long offset)
                || offset > RoomWire.MaximumCounter) throw RoomWire.Bad();
            RoomWire.Id(parts[0]); return (parts[0], offset);
        }
        var initial = Parse(bootstrap.CatalogCursor); var current = Parse(cursor);
        if (initial.Offset != 0 || initial.View != current.View) throw RoomWire.Bad();
        Offset = current.Offset;
    }
}

internal static class RoomMedia
{
    internal static MediaDescriptor Decode(JsonElement media)
    {
        string[] keys = ["v", "mediaId", "title", "titleKey", "fileSizeBytes", "durationMs"];
        bool hasHash = media.ValueKind == JsonValueKind.Object && media.TryGetProperty("fullHashSha256", out _);
        RoomWire.Keys(media, hasHash ? [.. keys, "fullHashSha256"] : keys);
        if (RoomWire.Integer(media, "v", 1) != 1) throw RoomWire.Bad();
        MediaDescriptor descriptor;
        try
        {
            descriptor = new(RoomWire.String(media, "mediaId"), RoomWire.String(media, "title"), RoomWire.String(media, "titleKey"),
                RoomWire.Integer(media, "fileSizeBytes"), media.GetProperty("durationMs").ValueKind == JsonValueKind.Null ? null : RoomWire.Integer(media, "durationMs"),
                hasHash ? RoomWire.String(media, "fullHashSha256") : null);
        }
        catch (ContractException) { throw RoomWire.Bad(); }
        return descriptor;
    }
}
