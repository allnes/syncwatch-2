using System.Text.Json;

namespace SyncWatch.Room;

/// <summary>The edition accepted at selection.changed, independent of later catalog revisions.</summary>
public sealed record RoomSelectionDefinition(string Epoch, long Sequence, long WatchGeneration, RoomCatalogEntry? Selection)
{
    public static RoomSelectionDefinition Decode(byte[] bytes, RoomBootstrap bootstrap)
    {
        using var document = RoomWire.Parse(bytes); var value = document.RootElement;
        RoomWire.Keys(value, "v", "roomEpoch", "sequence", "watchGeneration", "selection");
        long sequence = RoomWire.Integer(value, "sequence");
        if (RoomWire.Integer(value, "v", 1) != 1 || RoomWire.String(value, "roomEpoch") != bootstrap.Snapshot.Epoch
            || sequence < bootstrap.Snapshot.Sequence || RoomWire.Integer(value, "watchGeneration") != bootstrap.Snapshot.WatchGeneration) throw RoomWire.Bad();
        RoomCatalogEntry? selection = null;
        var entry = value.GetProperty("selection");
        if (entry.ValueKind != JsonValueKind.Null)
        {
            RoomWire.Keys(entry, "memberId", "media");
            string member = RoomWire.String(entry, "memberId"); RoomWire.Id(member);
            // The publishing member may have left since the selection was accepted.
            selection = new(member, RoomMedia.Decode(entry.GetProperty("media")));
        }
        if (selection?.Media.MediaId != bootstrap.Snapshot.MediaId) throw RoomWire.Bad();
        return new(bootstrap.Snapshot.Epoch, sequence, bootstrap.Snapshot.WatchGeneration, selection);
    }
}
