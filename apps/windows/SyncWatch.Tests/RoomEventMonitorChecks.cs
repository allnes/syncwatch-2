using SyncWatch;
using SyncWatch.Domain;
using SyncWatch.Room;

internal static class RoomEventMonitorChecks
{
    internal static async Task RunAsync(string address, string key)
    {
        await using var client = new RoomClient(new(address));
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        Task? monitoring = null;
        try
        {
            var identity = new RoomIdentity("run-" + Guid.NewGuid().ToString("N"), "Windows recovery");
            var admission = await client.CreateAsync(identity, new("syncplay.example.com", 8999, "Recovery"), new(key), cancellation.Token);
            var owner = new RoomMembershipSession(client, admission, identity);
            var media = new MediaDescriptor("movie", "Movie", "movie", 10, 60000, null);
            _ = await owner.PublishAsync([media], cancellation.Token);
            int deliveries = 0, recoveries = 0;
            monitoring = RoomEventMonitor.RunAsync(new(address), admission, owner, () => recoveries++, view =>
            {
                if (!view.Bootstrap.Snapshot.Members.Any(p => p.MemberId == admission.MemberId && p.Identity == identity)) throw new Exception("Recovery replaced identity");
                if (++deliveries == 1) throw new RoomProtocolException("transport");
            }, cancellation.Token);
            while (deliveries < 2) await Task.Delay(10, cancellation.Token);
            if (recoveries != 1) throw new Exception("Event transport was not rebound once");
            _ = await owner.PublishAsync([media], cancellation.Token);
            var context = await owner.WatchContextAsync(cancellation.Token);
            var selected = await owner.PerformAsync(new RoomCommandAction.Select(media.MediaId), context, cancellation.Token);
            if (selected.Definition.Selection?.Media != media) throw new Exception("Recovery reset command numbering");
            await cancellation.CancelAsync();
            try { await monitoring; } catch (OperationCanceledException) { }
            monitoring = null;
            int retries = 0;
            try
            {
                await RoomEventMonitor.RunAsync(new(address), admission, owner, () => retries++,
                    _ => throw new RoomProtocolException("malformed"), CancellationToken.None);
                throw new Exception("Malformed metadata was retried");
            }
            catch (RoomProtocolException error) when (error.Message == "malformed") { }
            if (retries != 0) throw new Exception("Invalid metadata triggered recovery");
            await client.LeaveAsync(admission);
            Console.WriteLine("SYNCWATCH_ROOM_EVENT_RECOVERY_OK retained identity/commands, terminal metadata, cancel/join");
        }
        finally
        {
            await cancellation.CancelAsync();
            if (monitoring is not null) { try { await monitoring; } catch (OperationCanceledException) { } }
        }
    }
}
