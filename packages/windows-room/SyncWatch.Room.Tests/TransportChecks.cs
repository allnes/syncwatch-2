using System.Text.Json;
using SyncWatch.Room;

internal static class TransportChecks
{
    internal static async Task RunAsync()
    {
        string? address = Environment.GetEnvironmentVariable("SYNCWATCH_ROOM_SERVICE"), key = Environment.GetEnvironmentVariable("SYNCWATCH_ROOM_CREATION_KEY");
        if (address is null || key is null) return;
        await using var owner = new RoomClient(new(address)); await using var guest = new RoomClient(new(address));
        var admission = await owner.CreateAsync(new("run-" + Guid.NewGuid().ToString("N"), "Windows owner"), new("syncplay.example.com", 8999, "Room check"), new(key));
        var events = await owner.OpenEventsAsync(admission);
        var initial = RoomBootstrap.InitialEvent(await events.ReceiveAsync(), admission);
        if (initial.Snapshot.Members.Count != 1) throw new Exception("initial membership");
        var empty = await owner.CatalogAsync(admission, initial, initial.CatalogCursor);
        if (empty.Items.Count != 0 || empty.NextCursor is not null) throw new Exception("empty catalog");
        var refreshed = await owner.SnapshotAsync(admission);
        bool invalidated = false;
        try { _ = await owner.CatalogAsync(admission, initial, initial.CatalogCursor); }
        catch (RoomProtocolException error) when (error.Message == "snapshotRequired") { invalidated = true; }
        if (!invalidated) throw new Exception("new bootstrap must invalidate preceding catalog");
        _ = await owner.CatalogAsync(admission, refreshed, refreshed.CatalogCursor);
        var joined = await guest.JoinAsync(admission.RoomId, admission.Invitation!, new("run-" + Guid.NewGuid().ToString("N"), "Windows guest"));
        var guestEvents = await guest.OpenEventsAsync(joined);
        if (RoomBootstrap.InitialEvent(await guestEvents.ReceiveAsync(), joined).Snapshot.Members.Count != 2) throw new Exception("guest membership");
        using (var document = JsonDocument.Parse(await events.ReceiveAsync()))
            if (document.RootElement.GetProperty("type").GetString() != "member.bound") throw new Exception("joined event");
        if ((await owner.SnapshotAsync(admission)).Snapshot.Members.Count != 2) throw new Exception("snapshot membership");
        await guest.LeaveAsync(joined);
        using (var document = JsonDocument.Parse(await events.ReceiveAsync()))
            if (document.RootElement.GetProperty("type").GetString() != "member.left") throw new Exception("left event");
        await owner.LeaveAsync(admission); await owner.DisposeAsync(); await owner.DisposeAsync();
        bool closed = false;
        try { _ = await owner.SnapshotAsync(admission); } catch (RoomProtocolException) { closed = true; }
        if (!closed) throw new Exception("closed client accepted work");
        Console.WriteLine("SYNCWATCH_ROOM_TRANSPORT_OK");
        await SeededCatalogAsync(address);
    }
    private static async Task SeededCatalogAsync(string address)
    {
        string? room = Environment.GetEnvironmentVariable("SYNCWATCH_CATALOG_ROOM"), invitation = Environment.GetEnvironmentVariable("SYNCWATCH_CATALOG_INVITATION");
        if (room is null || invitation is null) return;
        await using var client = new RoomClient(new(address));
        var admission = await client.JoinAsync(room, new(invitation), new("run-" + Guid.NewGuid().ToString("N"), "Windows catalog"));
        var events = await client.OpenEventsAsync(admission);
        var bootstrap = RoomBootstrap.InitialEvent(await events.ReceiveAsync(), admission);
        string? cursor = bootstrap.CatalogCursor; int pages = 0; HashSet<string> ids = [];
        while (cursor is not null)
        {
            var page = await client.CatalogAsync(admission, bootstrap, cursor);
            foreach (var entry in page.Items)
                if (entry.MemberId == admission.MemberId || !ids.Add(entry.Media.MediaId)) throw new Exception("catalog member/duplicate");
            if (++pages > 3) throw new Exception("catalog did not terminate");
            cursor = page.NextCursor;
        }
        if (pages != 3 || !ids.SetEquals(Enumerable.Range(0, 250).Select(i => "movie-" + i))) throw new Exception("catalog pages incomplete");
        await client.LeaveAsync(admission);
        Console.WriteLine("SYNCWATCH_ROOM_CATALOG_TRANSPORT_OK");
    }
}
