using SyncWatch.Room;

namespace SyncWatch;

// Replaces only the event transport; membership retains HTTP ownership and command numbering.
internal static class RoomEventMonitor
{
    internal static async Task RunAsync(RoomAddress address, RoomAdmission admission, RoomMembershipSession membership,
        Action reconnecting, Action<RoomCatalogView> accepted, CancellationToken cancellation)
    {
        int[] delays = [250, 500, 1000, 2000];
        int failures = 0;
        long? deadline = null;
        while (true)
        {
            cancellation.ThrowIfCancellationRequested();
            Exception failure;
            await using (var client = new RoomClient(address))
            {
                try
                {
                    long allowance = Math.Min(20000, deadline is long limit ? limit - Environment.TickCount64 : 20000);
                    if (allowance <= 0) throw new RoomProtocolException("transport");
                    RoomEventStream stream;
                    RoomCatalogView first;
                    using (var bootstrap = CancellationTokenSource.CreateLinkedTokenSource(cancellation))
                    {
                        bootstrap.CancelAfter(TimeSpan.FromMilliseconds(allowance));
                        stream = await client.OpenEventsAsync(admission, bootstrap.Token);
                        var initial = RoomBootstrap.InitialEvent(await stream.ReceiveAsync(bootstrap.Token), admission);
                        first = await membership.RefreshAsync(initial, cancellation: bootstrap.Token);
                    }
                    cancellation.ThrowIfCancellationRequested();
                    accepted(first); failures = 0; deadline = null;
                    var previous = first.Bootstrap.Snapshot;
                    while (true)
                    {
                        var update = RoomInvalidation.Decode(await stream.ReceiveAsync(cancellation));
                        if (update.Epoch != previous.Epoch) throw new RoomProtocolException("malformed");
                        if (update.Sequence <= previous.Sequence) continue;
                        var view = await membership.RefreshAsync(sequence: update.Sequence, cancellation: cancellation);
                        cancellation.ThrowIfCancellationRequested(); accepted(view); previous = view.Bootstrap.Snapshot;
                    }
                }
                catch (Exception error) { failure = error; }
            }
            cancellation.ThrowIfCancellationRequested();
            if (!RoomController.IsMetadataInterruption(failure) || failures >= delays.Length) throw failure;
            long until = deadline ??= Environment.TickCount64 + 25000;
            if (Environment.TickCount64 + delays[failures] >= until) throw failure;
            reconnecting(); await Task.Delay(delays[failures], cancellation); failures++;
        }
    }
}
