using System.Text.Json;
using SyncWatch.RoomMetadata;

internal static class SelectionChecks
{
    internal static void Run()
    {
        static JsonElement Json(object value) => Wire.Parse(JsonSerializer.SerializeToUtf8Bytes(value, Wire.Json));
        static void Check(bool value) { if (!value) throw new Exception("Frozen selection invariant"); }
        var store = new RoomStore(new() { CommandsPerSecond = 256 });
        var owner = store.Create(Json(new
        {
            v = 1,
            clientRunId = "run-owner",
            syncplayUsername = "owner",
            syncplayHost = "syncplay.example.invalid",
            syncplayPort = 8999,
            syncplayRoom = "selection"
        }));
        var guest = store.Join(owner.RoomId, Json(new
        {
            v = 1,
            invitation = owner.Invitation,
            clientRunId = "run-guest",
            syncplayUsername = "guest"
        }));
        Command Cmd(Admission member, long id, long generation, string type, object payload) => Wire.ReadCommand(
            JsonSerializer.SerializeToUtf8Bytes(new
            {
                v = 1,
                id = "cmd-" + id,
                type,
                roomEpoch = member.Bootstrap.Snapshot.RoomEpoch,
                clientRunId = member.MemberId == owner.MemberId ? "run-owner" : "run-guest",
                watchGeneration = generation,
                payload
            }, Wire.Json));
        Command Catalog(Admission member, long id, long generation, MediaDescriptor[] items) =>
            Cmd(member, id, generation, "catalog.updated", new { batchId = "batch-" + id, offset = 0, items, final = true });
        CommandResult Execute(Admission member, Command command) => store.Execute(owner.RoomId, member.Token, command);
        void Reject(Action action, string code)
        {
            try { action(); } catch (RoomException error) when (error.Code == code) { return; }
            throw new Exception("Expected selection rejection " + code);
        }
        Check(store.Selection(owner.RoomId, owner.Token, 0).Selection is null);
        var original = new MediaDescriptor(1, "movie-a", "Movie A", "movie a", 1024, 10000, new string('a', 64));
        Check(Execute(guest, Catalog(guest, 1, 0, [original])).Error is null);
        var choose = Cmd(owner, 1, 0, "selection.changed", new { mediaId = "movie-a" });
        var accepted = Execute(owner, choose); Check(accepted.Error is null);
        var frozen = store.Selection(owner.RoomId, owner.Token, 1);
        Check(frozen.Selection == new CatalogEntry(guest.MemberId, original));
        var snapshot = store.Snapshot(owner.RoomId, owner.Token);
        _ = store.Selection(owner.RoomId, owner.Token, 1);
        Check(store.Catalog(owner.RoomId, owner.Token, snapshot.CatalogCursor).Items.Single().Media == original);
        var changed = original with { FullHashSha256 = new string('b', 64), FileSizeBytes = 2048 };
        Check(Execute(guest, Catalog(guest, 2, 1, [changed])).Error is null);
        Check(store.Selection(owner.RoomId, owner.Token, 1).Selection == frozen.Selection);
        Check(Execute(owner, choose) == accepted); // A replay cannot recapture the changed catalog.
        store.Leave(owner.RoomId, guest.Token);
        Check(store.Selection(owner.RoomId, owner.Token, 1).Selection == frozen.Selection);
        Check(Execute(owner, Cmd(owner, 2, 1, "watch.started", new { mediaId = "movie-a" })).Error is null);
        Check(store.Selection(owner.RoomId, owner.Token, 2).Selection == frozen.Selection);
        Reject(() => store.Selection(owner.RoomId, owner.Token, 1), "staleGeneration");
        Reject(() => store.Selection(owner.RoomId, guest.Token, 2), "unauthorized");
        Check(Execute(owner, Cmd(owner, 3, 2, "watch.ended", new { reason = "user" })).Error is null);
        Check(store.Selection(owner.RoomId, owner.Token, 3).Selection == frozen.Selection);
        Check(Execute(owner, Cmd(owner, 4, 3, "watch.started", new { mediaId = "movie-a" })).Error is null);
        Check(store.Selection(owner.RoomId, owner.Token, 4).Selection == frozen.Selection);
        Check(Execute(owner, Cmd(owner, 5, 4, "selection.changed", new { mediaId = "absent" })).Error == "unavailable");
        Check(store.Selection(owner.RoomId, owner.Token, 4).Selection == frozen.Selection);
        var peer = store.Join(owner.RoomId, Json(new
        {
            v = 1,
            invitation = owner.Invitation,
            clientRunId = "run-guest",
            syncplayUsername = "guest"
        }));
        Check(Execute(owner, Catalog(owner, 6, 4, [original])).Error is null);
        Check(Execute(peer, Catalog(peer, 1, 4, [changed])).Error is null);
        Check(Execute(owner, Cmd(owner, 7, 4, "selection.changed", new { mediaId = "movie-a" })).Error == "conflict");
        Check(store.Selection(owner.RoomId, owner.Token, 4).Selection == frozen.Selection);
        Check(Execute(peer, Catalog(peer, 2, 4, [])).Error is null);
        Check(Execute(owner, Cmd(owner, 8, 4, "selection.changed", new { mediaId = "movie-a" })).Error is null);
        Check(store.Selection(owner.RoomId, owner.Token, 5).Selection == new CatalogEntry(owner.MemberId, original));
        store.Leave(owner.RoomId, owner.Token);
        Reject(() => store.Selection(owner.RoomId, peer.Token, 5), "unavailable");
        Console.WriteLine("SYNCWATCH_ROOM_SELECTION_OK");
    }
}
