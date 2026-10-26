using System.Text;
using System.Text.Json;
using SyncWatch.Domain;
using SyncWatch.Room;

internal static class CommandChecks
{
    private static RoomAdmission Admission(JsonElement root)
    {
        var entry = root.GetProperty("admissions").EnumerateArray().First(p => p.GetProperty("valid").GetBoolean());
        return RoomAdmission.Decode(Encoding.UTF8.GetBytes(entry.GetProperty("wire").GetString()!), new("run-room-client", "Room User"), true);
    }
    private static RoomCommandAction Action(JsonElement entry)
    {
        var payload = entry.GetProperty("payload");
        return entry.GetProperty("type").GetString() switch
        {
            "catalog.updated" => new RoomCommandAction.Catalog(payload.GetProperty("batchId").GetString()!, payload.GetProperty("offset").GetInt64(),
                payload.GetProperty("items").EnumerateArray().Select(p => new MediaDescriptor(p.GetProperty("mediaId").GetString()!, p.GetProperty("title").GetString()!,
                    p.GetProperty("titleKey").GetString()!, p.GetProperty("fileSizeBytes").GetInt64(), p.GetProperty("durationMs").ValueKind == JsonValueKind.Null ? null : p.GetProperty("durationMs").GetInt64(),
                    p.TryGetProperty("fullHashSha256", out var hash) ? hash.GetString() : null)).ToArray(), payload.GetProperty("final").GetBoolean()),
            "selection.changed" => new RoomCommandAction.Select(payload.GetProperty("mediaId").GetString()!),
            "watch.started" => new RoomCommandAction.Start(payload.GetProperty("mediaId").GetString()!),
            "watch.ended" => new RoomCommandAction.End(payload.GetProperty("reason").GetString() == "user" ? RoomWatchEndReason.User : RoomWatchEndReason.Finished),
            "media.missing" => new RoomCommandAction.Missing(payload.GetProperty("mediaId").GetString()!, payload.GetProperty("missing").GetBoolean()),
            "call.linkChanged" => new RoomCommandAction.Meet(payload.GetProperty("meetUri").GetString()),
            _ => throw new Exception("Unknown fixture command")
        };
    }
    internal static async Task RunAsync(JsonElement root)
    {
        var admission = Admission(root); var corpus = root.GetProperty("commands");
        foreach (var entry in corpus.GetProperty("outgoing").EnumerateArray())
        {
            RoomCommand? command = null;
            try { command = new(admission, entry.GetProperty("number").GetInt64(), entry.GetProperty("generation").GetInt64(), Action(entry)); }
            catch (RoomProtocolException) { }
            if ((command is not null) != entry.GetProperty("valid").GetBoolean()) throw new Exception("command: " + entry.GetProperty("name").GetString());
            if (command is null) continue;
            byte[] original = command.EncodedBytes, copy = command.EncodedBytes; copy[0] ^= 1;
            if (!original.SequenceEqual(command.EncodedBytes)) throw new Exception("command bytes mutated");
            using var actual = JsonDocument.Parse(original);
            using var expected = JsonDocument.Parse(JsonSerializer.SerializeToUtf8Bytes(new { v = 1, id = command.Id, type = entry.GetProperty("type").GetString(), clientRunId = "run-room-client", roomEpoch = "epoch-room", watchGeneration = entry.GetProperty("generation").GetInt64(), payload = entry.GetProperty("payload") }));
            if (!JsonElement.DeepEquals(actual.RootElement, expected.RootElement)) throw new Exception("command wire: " + entry.GetProperty("name").GetString());
        }
        var reference = new RoomCommand(admission, 1, 0, new RoomCommandAction.Select("movie-a"));
        foreach (var entry in corpus.GetProperty("results").EnumerateArray())
        {
            RoomCommandResult? result = null; byte[] bytes = Encoding.UTF8.GetBytes(entry.GetProperty("wire").GetString()!);
            try { result = RoomCommandResult.Decode(bytes, reference); } catch (RoomProtocolException) { }
            if ((result is not null) != entry.GetProperty("valid").GetBoolean()) throw new Exception("result: " + entry.GetProperty("name").GetString());
            if (result is not null)
            {
                using var wire = JsonDocument.Parse(bytes);
                if (result.Id != "cmd-1" || result.Sequence != 7 || result.ErrorCode != wire.RootElement.GetProperty("error").GetString()) throw new Exception("result fields");
            }
        }
        static void Rejected(System.Action run) { try { run(); } catch (RoomProtocolException) { return; } throw new Exception("Invalid command accepted"); }
        MediaDescriptor Media(int i, string title) => new("movie-" + i, title, MediaDescriptor.NormalizedTitleKey(title), 1, null, null);
        Rejected(() => _ = new RoomCommand(admission, 1, 0, new RoomCommandAction.Catalog("batch-a", 0, Enumerable.Range(0, 100).Select(i => Media(i, string.Concat(Enumerable.Repeat("😀", 256)))).ToArray(), true)));
        Rejected(() => _ = new RoomCommand(admission, 1, 0, new RoomCommandAction.Catalog("batch-a", 0, Enumerable.Range(0, 101).Select(i => Media(i, "Movie")).ToArray(), true)));
        Rejected(() => _ = new RoomCommand(admission, -1, 0, new RoomCommandAction.Select("movie-a")));
        Rejected(() => _ = new RoomCommand(admission, 1, 0, new RoomCommandAction.End((RoomWatchEndReason)999)));
        await using var client = new RoomClient(new("http://127.0.0.1:1"));
        bool bound = false;
        try { _ = await client.ExecuteAsync(admission with { RoomId = "room-other" }, reference); }
        catch (RoomProtocolException error) when (error.Message == "malformed") { bound = true; }
        if (!bound) throw new Exception("Foreign membership reached transport");
        Console.WriteLine("SYNCWATCH_ROOM_COMMANDS_OK");
    }
}
