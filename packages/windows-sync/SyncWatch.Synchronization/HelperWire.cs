using System.Text.Json;
using SyncWatch.Domain;

namespace SyncWatch.Synchronization;

internal sealed record HelperFrame(string Kind, string? Id, string? ReplyTo, ulong? AfterUserAction, JsonElement Payload, byte[] Bytes);

/// <summary>Strict incoming half of contracts/v1/helper-ipc; no engine or UI policy.</summary>
internal static class HelperWire
{
    internal static void Keys(JsonElement value, params string[] names)
    {
        if (value.ValueKind != JsonValueKind.Object) throw new IOException("malformed");
        HashSet<string> actual = [];
        foreach (var p in value.EnumerateObject()) if (!actual.Add(p.Name)) throw new IOException("duplicate-key");
        if (!actual.SetEquals(names)) throw new IOException("malformed");
    }
    internal static ulong Counter(JsonElement value)
    {
        if (!value.TryGetUInt64(out ulong result) || result > PlaybackScope.MaximumGeneration) throw new IOException("counter");
        return result;
    }
    internal static string Text(JsonElement value, int maximum)
    {
        string? text = value.GetString();
        if (string.IsNullOrEmpty(text) || text.EnumerateRunes().Count() > maximum || text.Any(c => c < 32 || c == 127)) throw new IOException("text");
        return text;
    }
    internal static long Position(JsonElement value)
    {
        if (!value.TryGetInt64(out long result) || result is < 0 or > WatchSession.MaximumPositionMs) throw new IOException("position");
        return result;
    }
    internal static bool Flag(JsonElement value) => value.ValueKind switch
    { JsonValueKind.True => true, JsonValueKind.False => false, _ => throw new IOException("boolean") };

    internal static HelperFrame Decode(byte[] bytes, PlaybackScope scope)
    {
        using JsonDocument document = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 8 });
        JsonElement root = document.RootElement;
        string kind = Text(root.GetProperty("type"), 64);
        bool correction = kind is "player.setPaused" or "player.setPosition" or "player.setSpeed" or "player.openFile";
        bool reply = kind is "bridge.ready" or "bridge.result" or "bridge.error" or "bridge.stopped";
        if (!correction && !reply && kind is not ("sync.connection" or "sync.readiness" or "sync.participants")) throw new IOException("direction");
        Keys(root, correction ? ["v", "type", "clientRunId", "mediaGeneration", "payload", "id", "afterUserAction"]
            : reply ? ["v", "type", "clientRunId", "mediaGeneration", "payload", "replyTo"]
            : ["v", "type", "clientRunId", "mediaGeneration", "payload", "id"]);
        if (root.GetProperty("v").GetInt32() != 1) throw new IOException("version");
        scope.Check(Text(root.GetProperty("clientRunId"), 64), Counter(root.GetProperty("mediaGeneration")));
        string identifier = Text(root.GetProperty(reply ? "replyTo" : "id"), 64);
        string prefix = reply || correction ? "cmd-" : "event-";
        if (!identifier.StartsWith(prefix, StringComparison.Ordinal) || !ulong.TryParse(identifier.AsSpan(prefix.Length), out ulong number)
            || number == 0 || number > PlaybackScope.MaximumGeneration || identifier != prefix + number) throw new IOException("identifier");
        JsonElement p = root.GetProperty("payload");
        switch (kind)
        {
            case "player.setPaused": Keys(p, "paused"); Flag(p.GetProperty("paused")); break;
            case "player.setPosition": Keys(p, "positionMs"); Position(p.GetProperty("positionMs")); break;
            case "player.setSpeed":
                Keys(p, "rate"); double rate = p.GetProperty("rate").GetDouble();
                if (!double.IsFinite(rate) || rate is < .25 or > 4) throw new IOException("rate"); break;
            case "player.openFile": Keys(p, "mediaHandle"); _ = new PlaybackScope(Text(p.GetProperty("mediaHandle"), 64), 0); break;
            case "bridge.ready":
                Keys(p, "syncplayRevision"); string revision = Text(p.GetProperty("syncplayRevision"), 40);
                if (revision.Length != 40 || revision.Any(c => !char.IsAsciiHexDigit(c) || char.IsUpper(c))) throw new IOException("revision"); break;
            case "bridge.result": Keys(p, "status"); if (p.GetProperty("status").GetString() != "applied") throw new IOException("result"); break;
            case "bridge.stopped": Keys(p); break;
            case "bridge.error":
                Keys(p, "code", "message", "retryable"); Text(p.GetProperty("code"), 64); Text(p.GetProperty("message"), 1024); Flag(p.GetProperty("retryable")); break;
            case "sync.connection":
                if (p.TryGetProperty("error", out _)) throw new IOException("connection-error");
                Keys(p, "state"); if (p.GetProperty("state").GetString() is not ("connecting" or "connected" or "disconnected")) throw new IOException("connection"); break;
            case "sync.readiness": Keys(p, "ready"); Flag(p.GetProperty("ready")); break;
            case "sync.participants":
                Keys(p, "participants"); var users = p.GetProperty("participants");
                if (users.ValueKind != JsonValueKind.Array || users.GetArrayLength() > 64) throw new IOException("participants");
                foreach (var user in users.EnumerateArray()) { Keys(user, "username", "ready"); Text(user.GetProperty("username"), 64); Flag(user.GetProperty("ready")); }
                break;
        }
        return new(kind, reply ? null : identifier, reply ? identifier : null,
            correction ? Counter(root.GetProperty("afterUserAction")) : null, p.Clone(), bytes);
    }
    internal static byte[] Encode(PlaybackScope scope, string kind, object payload, string? id = null,
        string? replyTo = null, ulong? userAction = null)
    {
        Dictionary<string, object?> frame = new()
        { ["v"] = 1, ["type"] = kind, ["clientRunId"] = scope.ClientRunId, ["mediaGeneration"] = scope.MediaGeneration, ["payload"] = payload };
        if (id is not null) frame["id"] = id;
        if (replyTo is not null) frame["replyTo"] = replyTo;
        if (kind == "player.state") { frame["origin"] = userAction is null ? "observation" : "user"; if (userAction is not null) frame["actionSequence"] = userAction; }
        return [.. JsonSerializer.SerializeToUtf8Bytes(frame), 10];
    }
}
