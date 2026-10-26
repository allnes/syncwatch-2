namespace SyncWatch.Room;

/// <summary>Ordered hint to fetch a snapshot. Payload data is never applied as state.</summary>
public sealed record RoomInvalidation(string Epoch, long Sequence)
{
    public static RoomInvalidation Decode(ReadOnlyMemory<byte> bytes)
    {
        using var document = RoomWire.Parse(bytes); var value = document.RootElement;
        RoomWire.Keys(value, "v", "type", "roomEpoch", "sequence", "memberId", "clientRunId", "watchGeneration", "payload");
        if (RoomWire.Integer(value, "v", 1) != 1 || RoomWire.String(value, "type") is not
            ("member.bound" or "member.left" or "catalog.updated" or "selection.changed" or "watch.started" or "watch.ended" or "media.missing" or "call.linkChanged")
            || value.GetProperty("payload").ValueKind != System.Text.Json.JsonValueKind.Object) throw RoomWire.Bad();
        string epoch = RoomWire.String(value, "roomEpoch"); RoomWire.Id(epoch); RoomWire.Id(RoomWire.String(value, "memberId")); RoomWire.Id(RoomWire.String(value, "clientRunId"));
        _ = RoomWire.Integer(value, "watchGeneration"); return new(epoch, RoomWire.Integer(value, "sequence"));
    }
}
