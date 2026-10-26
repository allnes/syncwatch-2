using System.Text;
using System.Text.Json;
using SyncWatch.Room;

internal static class CatalogViewChecks
{
    internal static async Task RunAsync(JsonElement fixture)
    {
        var bootstrap = RoomBootstrap.Decode(Encoding.UTF8.GetBytes(fixture.GetProperty("catalogBootstrap").GetString()!));
        foreach (var item in fixture.GetProperty("catalogViews").EnumerateArray())
        {
            string[] pages = item.GetProperty("pages").EnumerateArray().Select(p => p.GetString()!).ToArray();
            bool valid = item.GetProperty("valid").GetBoolean(), accepted = false;
            try
            {
                var result = await ReadAsync(bootstrap, pages);
                accepted = true;
                if (result.Bootstrap != bootstrap || result.Items.Count != item.GetProperty("count").GetInt32()) throw new Exception("Complete view facts");
                if (result.Items is IList<RoomCatalogEntry> mutable && !mutable.IsReadOnly) throw new Exception("Mutable complete view");
            }
            catch (RoomProtocolException) { }
            if (valid != accepted) throw new Exception("catalog view: " + item.GetProperty("name").GetString());
        }
        foreach (int count in new[] { 2048, 2049 })
        {
            List<string> pages = [];
            for (int start = 0; start < count; start += 100)
            {
                int end = Math.Min(start + 100, count);
                pages.Add(JsonSerializer.Serialize(new
                {
                    v = 1,
                    roomEpoch = "epoch-room",
                    sequence = 7,
                    items = Enumerable.Range(start, end - start).Select(index => new { memberId = "member-owner", media = new { v = 1, mediaId = $"movie-{index}", title = "Movie", titleKey = "movie", fileSizeBytes = 1024, durationMs = (long?)null } }),
                    nextCursor = end < count ? $"view-1:{end}" : null
                }));
            }
            bool accepted = false;
            try { accepted = (await ReadAsync(bootstrap, pages)).Items.Count == count; }
            catch (RoomProtocolException) { }
            if (accepted != (count == 2048)) throw new Exception("Per-member catalog bound");
        }
        byte[] terminal = Encoding.UTF8.GetBytes("{\"v\":1,\"roomEpoch\":\"epoch-room\",\"sequence\":7,\"items\":[],\"nextCursor\":null}");
        using var cancelled = new CancellationTokenSource();
        try
        {
            await RoomCatalogView.ReadAsync(bootstrap, (_, _) => { cancelled.Cancel(); return Task.FromResult(terminal); }, cancelled.Token);
            throw new Exception("Cancelled final page escaped");
        }
        catch (OperationCanceledException) { }
        try
        {
            await RoomCatalogView.ReadAsync(bootstrap, (_, _) => throw new RoomProtocolException("snapshotRequired"));
            throw new Exception("Expired cursor returned partial state");
        }
        catch (RoomProtocolException error) when (error.Message == "snapshotRequired") { }
        Console.WriteLine("SYNCWATCH_ROOM_CATALOG_VIEW_OK complete/duplicate/version/bound/cancellation/expiry");
    }

    private static async Task<RoomCatalogView> ReadAsync(RoomBootstrap bootstrap, IReadOnlyList<string> pages)
    {
        int index = 0;
        var result = await RoomCatalogView.ReadAsync(bootstrap, (cursor, _) =>
        {
            if (index >= pages.Count) throw new Exception("Unexpected catalog request");
            using var previous = index > 0 ? JsonDocument.Parse(pages[index - 1]) : null;
            string? expected = index == 0 ? "view-1:0" : previous!.RootElement.GetProperty("nextCursor").GetString();
            if (cursor != expected) throw new Exception("Unexpected cursor order");
            return Task.FromResult(Encoding.UTF8.GetBytes(pages[index++]));
        });
        if (index != pages.Count) throw new Exception("Missing catalog page");
        return result;
    }
}
