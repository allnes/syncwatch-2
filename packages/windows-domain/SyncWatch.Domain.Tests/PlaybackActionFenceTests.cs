using System.Globalization;
using System.Text.Json;
using SyncWatch.Domain;

internal static class PlaybackActionFenceTests
{
    public static void Run(string directory)
    {
        using var document = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(directory, "playback-authority.json")));
        var initial = document.RootElement.GetProperty("scope");
        var scope = new PlaybackScope(initial.GetProperty("clientRunId").GetString()!, initial.GetProperty("mediaGeneration").GetUInt64());
        var cases = document.RootElement.GetProperty("cases");
        Check(cases.GetArrayLength() == 5);
        foreach (var fixture in cases.EnumerateArray())
        {
            var fence = new PlaybackActionFence(scope);
            foreach (var step in fixture.GetProperty("steps").EnumerateArray())
            {
                var owner = new PlaybackScope(step.TryGetProperty("ownerRunId", out var run) ? run.GetString()! : scope.ClientRunId,
                    step.TryGetProperty("ownerGeneration", out var generation) ? generation.GetUInt64() : scope.MediaGeneration);
                var before = (fence.IssuedSequence, fence.PublishedSequence, fence.Invalidated);
                string result = ""; string? errorCode = null;
                try
                {
                    switch (step.GetProperty("op").GetString())
                    {
                        case "begin": result = fence.BeginUserAction(owner).ToString(CultureInfo.InvariantCulture); break;
                        case "canPublish": result = fence.CanPublish(step.GetProperty("sequence").GetUInt64(), owner).ToString().ToLowerInvariant(); break;
                        case "publish":
                            var status = step.TryGetProperty("status", out var state) && state.GetString() == "loading" ? PlaybackStatus.Loading : PlaybackStatus.Ready;
                            var observation = new PlaybackObservation { Scope = owner, Status = status, Paused = true, Seekable = status == PlaybackStatus.Ready, DurationMs = status == PlaybackStatus.Ready ? 4000 : null };
                            result = fence.DidPublish(step.GetProperty("sequence").GetUInt64(), observation).ToString().ToLowerInvariant(); break;
                        case "correction": result = LowerFirst(fence.Correction(owner, step.GetProperty("afterUserAction").GetUInt64()).ToString()); break;
                        case "invalidate": fence.Invalidate(); break;
                        default: throw new InvalidOperationException("Unknown authority fixture");
                    }
                }
                catch (ContractException error) { errorCode = LowerFirst(error.Rejection.ToString()); }
                catch (WatchException error) { errorCode = LowerFirst(error.Rejection.ToString()); }
                string? expected = step.TryGetProperty("error", out var rejection) ? rejection.GetString() : null;
                Check(errorCode == expected);
                if (errorCode is null) Check(result == (step.TryGetProperty("result", out var output) ? output.GetString() : ""));
                else Check(before == (fence.IssuedSequence, fence.PublishedSequence, fence.Invalidated));
            }
        }
        Console.WriteLine("SYNCWATCH_NATIVE_ACTION_ORDERING_OK");
    }
    private static string LowerFirst(string value) => char.ToLowerInvariant(value[0]) + value[1..];
    private static void Check(bool value) { if (!value) throw new InvalidOperationException("Native action ordering corpus"); }
}
