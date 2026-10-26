using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using SyncWatch.Domain;

namespace SyncWatch.Room;

public sealed record RoomCatalogEntry(string MemberId, MediaDescriptor Media);

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
            string member = RoomWire.String(entry, "memberId"); var media = entry.GetProperty("media");
            string[] keys = ["v", "mediaId", "title", "titleKey", "fileSizeBytes", "durationMs"];
            bool hasHash = media.ValueKind == JsonValueKind.Object && media.TryGetProperty("fullHashSha256", out _);
            RoomWire.Keys(media, hasHash ? [.. keys, "fullHashSha256"] : keys);
            if (!members.Contains(member) || RoomWire.Integer(media, "v", 1) != 1) throw RoomWire.Bad();
            MediaDescriptor descriptor;
            try
            {
                descriptor = new(RoomWire.String(media, "mediaId"), RoomWire.String(media, "title"), RoomWire.String(media, "titleKey"),
                    RoomWire.Integer(media, "fileSizeBytes"), media.GetProperty("durationMs").ValueKind == JsonValueKind.Null ? null : RoomWire.Integer(media, "durationMs"),
                    hasHash ? RoomWire.String(media, "fullHashSha256") : null);
            }
            catch (ContractException) { throw RoomWire.Bad(); }
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
