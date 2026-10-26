using SyncWatch;
using SyncWatch.Domain;
using SyncWatch.Room;

internal static class RoomWatchContextChecks
{
    internal static async Task RunAsync()
    {
        string? address = Environment.GetEnvironmentVariable("SYNCWATCH_ROOM_SERVICE"), key = Environment.GetEnvironmentVariable("SYNCWATCH_ROOM_CREATION_KEY");
        if (address is null || key is null) return;
        await using var client = new RoomClient(new(address)); await using var peer = new RoomClient(new(address));
        var identity = new RoomIdentity("run-" + Guid.NewGuid().ToString("N"), "Windows watch");
        var admission = await client.CreateAsync(identity, new("syncplay.example.com", 8999, "Watch context"), new(key));
        var stream = await client.OpenEventsAsync(admission);
        _ = RoomBootstrap.InitialEvent(await stream.ReceiveAsync(), admission);
        var owner = new RoomMembershipSession(client, admission, identity);
        var descriptor = new MediaDescriptor("movie-a", "Movie", "movie", 1000, 60000, new string('a', 64));
        _ = await owner.PublishAsync([descriptor]);
        var idle = await owner.WatchContextAsync();
        if (idle.Definition.Selection is not null) throw new Exception("Initial watch selection");
        var selected = await owner.PerformAsync(new RoomCommandAction.Select("movie-a"), idle);
        if (selected.Definition.Selection?.Media != descriptor) throw new Exception("Selected edition");
        _ = await owner.PublishAsync([]);
        if ((await owner.WatchContextAsync()).Definition.Selection?.Media != descriptor) throw new Exception("Mutable catalog redefined selection");
        var peerIdentity = new RoomIdentity("run-" + Guid.NewGuid().ToString("N"), "Windows peer");
        var joined = await peer.JoinAsync(admission.RoomId, admission.Invitation!, peerIdentity);
        var peerStream = await peer.OpenEventsAsync(joined);
        _ = RoomBootstrap.InitialEvent(await peerStream.ReceiveAsync(), joined);
        var peerOwner = new RoomMembershipSession(peer, joined, peerIdentity);
        _ = await peerOwner.PublishAsync([descriptor]);
        _ = await peerOwner.PerformAsync(new RoomCommandAction.Select("movie-a"), await peerOwner.WatchContextAsync());
        bool stale = false;
        try { _ = await owner.PerformAsync(new RoomCommandAction.Start("movie-a"), selected); }
        catch (RoomProtocolException error) when (error.Message == "staleGeneration") { stale = true; }
        if (!stale) throw new Exception("Stale user intent overwrote peer generation");
        var active = await owner.PerformAsync(new RoomCommandAction.Start("movie-a"), await owner.WatchContextAsync());
        if (active.Bootstrap.Snapshot.WatchStatus != "active" || active.Definition.Selection?.MemberId != joined.MemberId) throw new Exception("Start definition");
        _ = await owner.PerformAsync(new RoomCommandAction.End(RoomWatchEndReason.User), active);
        await peer.LeaveAsync(joined); await client.LeaveAsync(admission);
        Console.WriteLine("SYNCWATCH_ROOM_WATCH_CONTEXT_OK");
    }
}
