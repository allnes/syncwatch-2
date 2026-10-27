using System.Globalization;
using SyncWatch.Domain;
using SyncWatch.Room;

internal static class CommandTransportChecks
{
    internal static async Task RunAsync(string address, string key)
    {
        await using var owner = new RoomClient(new(address)); await using var guest = new RoomClient(new(address));
        var admission = await owner.CreateAsync(new("run-" + Guid.NewGuid().ToString("N"), "Windows commands"), new("syncplay.example.com", 8999, "Commands check"), new(key));
        var events = await owner.OpenEventsAsync(admission);
        _ = RoomBootstrap.InitialEvent(await events.ReceiveAsync(), admission);
        var catalog = Enumerable.Range(0, 250).Select(i => new MediaDescriptor("movie-" + i, "Movie " + i, "movie " + i, 1024 + i, 60000, i.ToString("x64", CultureInfo.InvariantCulture))).ToArray();
        for (int index = 0; index < 3; index++)
        {
            var command = new RoomCommand(admission, index + 1, 0, new RoomCommandAction.Catalog("batch-native", index * 100, catalog.Skip(index * 100).Take(100).ToArray(), index == 2));
            var first = await owner.ExecuteAsync(admission, command); var replay = await owner.ExecuteAsync(admission, command);
            if (first.ErrorCode is not null || first != replay) throw new Exception("catalog exact-byte replay");
            if (index == 0)
            {
                var partial = await owner.SnapshotAsync(admission);
                if ((await owner.CatalogAsync(admission, partial, partial.CatalogCursor)).Items.Count != 0) throw new Exception("partial catalog was published");
            }
        }
        var view = await owner.SnapshotAsync(admission); string? cursor = view.CatalogCursor; HashSet<string> ids = [];
        while (cursor is not null)
        {
            var page = await owner.CatalogAsync(admission, view, cursor);
            foreach (var item in page.Items) if (item.MemberId != admission.MemberId || !ids.Add(item.Media.MediaId)) throw new Exception("native catalog identity");
            cursor = page.NextCursor;
        }
        if (!ids.SetEquals(catalog.Select(p => p.MediaId))) throw new Exception("native catalog incomplete");
        var selection = new RoomCommand(admission, 4, 0, new RoomCommandAction.Select("movie-0"));
        var selected = await owner.ExecuteAsync(admission, selection);
        if (selected.ErrorCode is not null || selected != await owner.ExecuteAsync(admission, selection)) throw new Exception("selection replay");
        var selectedView = await owner.SnapshotAsync(admission);
        var definition = await owner.SelectionAsync(admission, selectedView);
        if (definition.Selection?.MemberId != admission.MemberId || definition.Selection.Media != catalog[0]) throw new Exception("frozen selection descriptor");
        _ = await owner.CatalogViewAsync(admission, selectedView);
        bool staleSelection = false;
        try { _ = await owner.SelectionAsync(admission, view); }
        catch (RoomProtocolException error) when (error.Message == "staleGeneration") { staleSelection = true; }
        if (!staleSelection) throw new Exception("Stale selection lookup was accepted");
        bool conflict = false;
        try { _ = await owner.ExecuteAsync(admission, new(admission, 4, 0, new RoomCommandAction.Select("movie-1"))); }
        catch (RoomProtocolException error) when (error.Message == "conflict") { conflict = true; }
        if (!conflict) throw new Exception("Changed content under the same command ID was accepted");
        if ((await owner.ExecuteAsync(admission, new(admission, 5, 0, new RoomCommandAction.Select("movie-1")))).ErrorCode != "staleGeneration") throw new Exception("stale command generation");
        foreach (var command in new[] { new RoomCommand(admission, 6, 1, new RoomCommandAction.Start("movie-0")), new(admission, 7, 2, new RoomCommandAction.Missing("movie-0", true)), new(admission, 8, 2, new RoomCommandAction.End(RoomWatchEndReason.User)), new(admission, 9, 3, new RoomCommandAction.Meet("https://meet.google.com/abc-defg-hij")), new(admission, 10, 3, new RoomCommandAction.Meet(null)) })
            if ((await owner.ExecuteAsync(admission, command)).ErrorCode is not null) throw new Exception("typed metadata command rejected");
        var final = await owner.SnapshotAsync(admission);
        if (final.Snapshot.WatchStatus != "ended" || final.Snapshot.WatchGeneration != 3 || final.Snapshot.MeetUri is not null || !final.MissingMembers.Contains(admission.MemberId)) throw new Exception("authoritative metadata state");
        var joined = await guest.JoinAsync(admission.RoomId, admission.Invitation!, new("run-" + Guid.NewGuid().ToString("N"), "Windows command guest"));
        var guestEvents = await guest.OpenEventsAsync(joined); _ = RoomBootstrap.InitialEvent(await guestEvents.ReceiveAsync(), joined);
        if ((await guest.ExecuteAsync(joined, new(joined, 1, 3, new RoomCommandAction.Meet(null)))).ErrorCode != "forbidden") throw new Exception("guest owner command accepted");
        bool bound = false;
        try { _ = await guest.ExecuteAsync(joined, selection); } catch (RoomProtocolException error) when (error.Message == "malformed") { bound = true; }
        if (!bound) throw new Exception("foreign command membership accepted");
        await guest.LeaveAsync(joined); await owner.LeaveAsync(admission);
        Console.WriteLine("SYNCWATCH_ROOM_COMMAND_TRANSPORT_OK");
    }
}
