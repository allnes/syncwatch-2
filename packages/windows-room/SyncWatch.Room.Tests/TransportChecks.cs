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
        if (RoomBootstrap.InitialEvent(await events.ReceiveAsync(), admission).Snapshot.Members.Count != 1) throw new Exception("initial membership");
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
    }
}
