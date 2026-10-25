using System.Text;
using System.Text.Json;
using SyncWatch.Bridge;
using SyncWatch.Domain;

internal static class PlayerCorrectionChecks
{
    internal static void Run(string path)
    {
        HelperSessionChecks.Run();
        HelperCommandsChecks.Run(Path.Combine(Path.GetDirectoryName(path)!, "helper-commands.json"));
        HelperReplyChecks.Run(Path.Combine(Path.GetDirectoryName(path)!, "helper-replies.json"));
        using var corpus = JsonDocument.Parse(File.ReadAllBytes(path));
        var cases = corpus.RootElement.GetProperty("cases");
        if (cases.GetArrayLength() != 49) throw new InvalidDataException("Incomplete helper/player corpus");
        var scope = new PlaybackScope("helper-run", 7);
        foreach (var fixture in cases.EnumerateArray())
        {
            byte[] frame = fixture.TryGetProperty("hex", out var hex) ? Convert.FromHexString(hex.GetString()!) : Encoding.UTF8.GetBytes(fixture.GetProperty("frame").GetString()!);
            bool accepted = false;
            try
            {
                var command = PlayerCorrection.Decode(frame, scope);
                if (command.Id != "cmd-9" || command.AfterUserAction != (fixture.GetProperty("name").GetString() == "legacy-zero-watermark" ? 0UL : 3UL)) throw new InvalidDataException("Wrong command identity");
                accepted = true;
            }
            catch (Exception error) when (error is PlayerCorrectionException or ContractException or JsonException or DecoderFallbackException) { }
            if (accepted != fixture.GetProperty("accepted").GetBoolean()) throw new InvalidDataException(fixture.GetProperty("name").GetString());
        }
        var first = cases.EnumerateArray().First(value => value.GetProperty("name").GetString() == "player.setPosition");
        var request = PlayerCorrection.Decode(Encoding.UTF8.GetBytes(first.GetProperty("frame").GetString()!), scope);
        var native = new PlaybackScope("native-owner", 2);
        var actual = new PlaybackObservation { Scope = native, Sequence = 9, Status = PlaybackStatus.Ready, PositionMs = 1300, DurationMs = 4000, Paused = true, Rate = 1, Seekable = true };
        using var result = JsonDocument.Parse(request.Result(actual, native));
        if (result.RootElement.GetProperty("clientRunId").GetString() != scope.ClientRunId || result.RootElement.GetProperty("replyTo").GetString() != "cmd-9" || result.RootElement.GetProperty("payload").GetProperty("positionMs").GetInt64() != 1300) throw new InvalidDataException("Requested target became an observation");
        try { request.Result(actual, scope); throw new InvalidDataException("Foreign native observation accepted"); }
        catch (ContractException) { }
        Console.WriteLine("SYNCWATCH_HELPER_PLAYER_OK 49 frames; actual result and independent native ownership");
    }
}
