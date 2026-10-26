using SyncWatch.Domain;

namespace SyncWatch.Room;

public enum RoomWatchEndReason { User, Finished }
public abstract record RoomCommandAction
{
    private RoomCommandAction() { }
    public sealed record Catalog(string BatchId, long Offset, IReadOnlyList<MediaDescriptor> Items, bool Final) : RoomCommandAction;
    public sealed record Select(string MediaId) : RoomCommandAction;
    public sealed record Start(string MediaId) : RoomCommandAction;
    public sealed record End(RoomWatchEndReason Reason) : RoomCommandAction;
    public sealed record Missing(string MediaId, bool IsMissing) : RoomCommandAction;
    public sealed record Meet(string? Uri) : RoomCommandAction;
}

/// <summary>Retain until the result is known; retries reuse the original bytes.
/// The application owns monotonically increasing numbers for the membership.</summary>
public sealed class RoomCommand
{
    public string Id { get; }
    private readonly byte[] wire;
    public byte[] EncodedBytes => wire.ToArray();
    private readonly string roomId, memberId, runId, epoch;
    public RoomCommand(RoomAdmission admission, long number, long watchGeneration, RoomCommandAction action)
    {
        if (number is < 1 or > RoomWire.MaximumCounter || watchGeneration is < 0 or > RoomWire.MaximumCounter) throw RoomWire.Bad();
        roomId = admission.RoomId; memberId = admission.MemberId; epoch = admission.Bootstrap.Snapshot.Epoch;
        runId = admission.Bootstrap.Snapshot.Members.FirstOrDefault(p => p.MemberId == memberId)?.Identity.ClientRunId ?? throw RoomWire.Bad();
        foreach (string value in new[] { roomId, memberId, epoch, runId }) RoomWire.Id(value);
        Id = "cmd-" + number.ToString(System.Globalization.CultureInfo.InvariantCulture);
        string type; object payload;
        switch (action)
        {
            case RoomCommandAction.Catalog catalog:
                RoomWire.Id(catalog.BatchId);
                var items = catalog.Items.Take(101).ToArray();
                if (items.Length > 100 || catalog.Offset < 0 || catalog.Offset > RoomWire.MaximumCounter - items.Length
                    || items.Select(p => p.MediaId).Distinct(StringComparer.Ordinal).Count() != items.Length) throw RoomWire.Bad();
                type = "catalog.updated"; payload = new { batchId = catalog.BatchId, offset = catalog.Offset, items = items.Select(Media).ToArray(), final = catalog.Final };
                break;
            case RoomCommandAction.Select select:
                RoomWire.Id(select.MediaId); type = "selection.changed"; payload = new { mediaId = select.MediaId }; break;
            case RoomCommandAction.Start start:
                RoomWire.Id(start.MediaId); type = "watch.started"; payload = new { mediaId = start.MediaId }; break;
            case RoomCommandAction.End end:
                type = "watch.ended"; payload = new { reason = end.Reason switch { RoomWatchEndReason.User => "user", RoomWatchEndReason.Finished => "finished", _ => throw RoomWire.Bad() } }; break;
            case RoomCommandAction.Missing missing:
                RoomWire.Id(missing.MediaId); type = "media.missing"; payload = new { mediaId = missing.MediaId, missing = missing.IsMissing }; break;
            case RoomCommandAction.Meet meet:
                RoomWire.ValidateMeetUri(meet.Uri);
                type = "call.linkChanged"; payload = new { meetUri = meet.Uri }; break;
            default: throw RoomWire.Bad();
        }
        wire = RoomWire.Encode(new { v = 1, id = Id, type, clientRunId = runId, roomEpoch = epoch, watchGeneration, payload });
    }
    internal void Verify(RoomAdmission admission)
    {
        if (admission.RoomId != roomId || admission.MemberId != memberId || admission.Bootstrap.Snapshot.Epoch != epoch
            || admission.Bootstrap.Snapshot.Members.FirstOrDefault(p => p.MemberId == memberId)?.Identity.ClientRunId != runId) throw RoomWire.Bad();
    }
    private static Dictionary<string, object?> Media(MediaDescriptor value)
    {
        Dictionary<string, object?> fields = new()
        {
            ["v"] = 1,
            ["mediaId"] = value.MediaId,
            ["title"] = value.Title,
            ["titleKey"] = value.TitleKey,
            ["fileSizeBytes"] = value.FileSizeBytes,
            ["durationMs"] = value.DurationMs
        };
        if (value.FullHashSha256 is not null) fields["fullHashSha256"] = value.FullHashSha256;
        return fields;
    }
}

public sealed record RoomCommandResult
{
    public string Id { get; }
    public long Sequence { get; }
    public string? ErrorCode { get; }
    private RoomCommandResult(string id, long sequence, string? errorCode) { Id = id; Sequence = sequence; ErrorCode = errorCode; }
    public static RoomCommandResult Decode(ReadOnlyMemory<byte> bytes, RoomCommand command)
    {
        using var document = RoomWire.Parse(bytes); var value = document.RootElement;
        RoomWire.Keys(value, "v", "type", "id", "sequence", "error");
        if (RoomWire.Integer(value, "v", 1) != 1 || RoomWire.String(value, "type") != "command.result" || RoomWire.String(value, "id") != command.Id) throw RoomWire.Bad();
        string? error = RoomWire.OptionalString(value.GetProperty("error"));
        string[] allowed = ["foreignRun", "staleEpoch", "staleGeneration", "unavailable", "conflict", "queueFull", "invalidState", "forbidden", "malformed", "frameTooLarge"];
        if (error is not null && !allowed.Contains(error, StringComparer.Ordinal)) throw RoomWire.Bad();
        return new(command.Id, RoomWire.Integer(value, "sequence"), error);
    }
}
