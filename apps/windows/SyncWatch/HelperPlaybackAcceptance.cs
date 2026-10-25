using System.IO;
using System.Text.Json;
using SyncWatch.Bridge;
using SyncWatch.Domain;

namespace SyncWatch;

// Explicit native boundary check; no helper/server connection is established.
internal static class HelperPlaybackAcceptance
{
    internal static async Task RunAsync(IPlaybackPort player, PlaybackScope scope)
    {
        var wire = new PlaybackScope("helper-run", 7);
        PlayerCorrection Command(int id, string type, object payload) => PlayerCorrection.Decode(JsonSerializer.SerializeToUtf8Bytes(new
        { v = 1, id = "cmd-" + id, type, clientRunId = wire.ClientRunId, mediaGeneration = wire.MediaGeneration, afterUserAction = 0, payload }).Concat(new byte[] { 10 }).ToArray(), wire);
        async Task Until(Func<PlaybackObservation, bool> predicate)
        {
            var clock = System.Diagnostics.Stopwatch.StartNew();
            while (clock.Elapsed < TimeSpan.FromSeconds(3)) { if (predicate(await player.ObserveAsync(scope))) return; await Task.Delay(40); }
            throw new TimeoutException("native helper correction");
        }
        await Until(value => value.Status == PlaybackStatus.Ready && value.Paused && value.Seekable);
        var seek = Command(1, "player.setPosition", new { positionMs = 2000 });
        var actual = await seek.ApplyAsync(player, scope, "media-1");
        using var result = JsonDocument.Parse(seek.Result(actual, scope));
        if (result.RootElement.GetProperty("clientRunId").GetString() != wire.ClientRunId || result.RootElement.GetProperty("payload").GetProperty("positionMs").GetInt64() != actual.PositionMs) throw new InvalidDataException("requested target acknowledged");
        await Until(value => Math.Abs(value.PositionMs - 2000) < 200);
        await Command(2, "player.setPaused", new { paused = false }).ApplyAsync(player, scope, "media-1");
        await Until(value => !value.Paused);
        await Command(3, "player.setPaused", new { paused = true }).ApplyAsync(player, scope, "media-1");
        await Until(value => value.Paused);
        await Command(4, "player.setSpeed", new { rate = 1.25 }).ApplyAsync(player, scope, "media-1");
        await Until(value => Math.Abs(value.Rate - 1.25) < .001);
        var before = await player.ObserveAsync(scope);
        var kept = await Command(5, "player.openFile", new { mediaHandle = "media-1" }).ApplyAsync(player, scope, "media-1");
        if (!kept.Paused || Math.Abs(kept.PositionMs - before.PositionMs) >= 100) throw new InvalidDataException("owned media reopened");
        try { await Command(6, "player.openFile", new { mediaHandle = "media-other" }).ApplyAsync(player, scope, "media-1"); throw new InvalidDataException("foreign media accepted"); }
        catch (PlayerCorrectionException error) when (error.Message == "unauthorizedHandle") { }
    }
}
