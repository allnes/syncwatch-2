using SyncWatch;
using SyncWatch.Domain;
using SyncWatch.Room;

internal static class RoomEventMonitorChecks
{
    internal static async Task RunAsync(string address, string key)
    {
        await using var client = new RoomClient(new(address));
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        Task? monitoring = null, publishing = null;
        try
        {
            var identity = new RoomIdentity("run-" + Guid.NewGuid().ToString("N"), "Windows recovery");
            var admission = await client.CreateAsync(identity, new("syncplay.example.com", 8999, "Recovery"), new(key), cancellation.Token);
            var owner = new RoomMembershipSession(client, admission, identity);
            var media = new MediaDescriptor("movie", "Movie", "movie", 10, 60000, null);
            _ = await owner.PublishAsync([media], cancellation.Token);
            var corpus = Enumerable.Range(0, 120).Select(index => new MediaDescriptor("extra-" + index, "Extra", "extra", 10, 60000, null));
            publishing = owner.PublishAsync(new[] { media }.Concat(corpus).ToArray(), cancellation.Token);
            int deliveries = 0, recoveries = 0;
            monitoring = RoomEventMonitor.RunAsync(new(address), owner, () => recoveries++, view =>
            {
                if (!view.Bootstrap.Snapshot.Members.Any(p => p.MemberId == admission.MemberId && p.Identity == identity)) throw new Exception("Recovery replaced identity");
                if (++deliveries == 1) throw new RoomProtocolException("transport");
            }, cancellation.Token);
            await publishing; publishing = null;
            while (deliveries < 2) await Task.Delay(10, cancellation.Token);
            if (recoveries != 1) throw new Exception("Event transport was not rebound once");
            _ = await owner.PublishAsync([media], cancellation.Token);
            var context = await owner.WatchContextAsync(cancellation.Token);
            var selected = await owner.PerformAsync(new RoomCommandAction.Select(media.MediaId), context, cancellation.Token);
            if (selected.Definition.Selection?.Media != media) throw new Exception("Recovery reset command numbering");
            await cancellation.CancelAsync();
            try { await monitoring; } catch (OperationCanceledException) { }
            monitoring = null;
            int exhaustedAttempts = 0, exhaustedRetries = 0;
            try
            {
                await RoomEventMonitor.RunAsync(new(address), owner, () => exhaustedRetries++,
                    _ => { exhaustedAttempts++; throw new RoomProtocolException("transport"); }, CancellationToken.None);
                throw new Exception("Transport retries were not bounded");
            }
            catch (RoomProtocolException error) when (error.Message == "transport") { }
            if (exhaustedAttempts != 6 || exhaustedRetries != 5) throw new Exception("Recovery exceeded its attempt budget");
            int retries = 0;
            try
            {
                await RoomEventMonitor.RunAsync(new(address), owner, () => retries++,
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
            if (publishing is not null) { try { await publishing; } catch (OperationCanceledException) { } }
            if (monitoring is not null) { try { await monitoring; } catch (OperationCanceledException) { } }
        }
    }
}
