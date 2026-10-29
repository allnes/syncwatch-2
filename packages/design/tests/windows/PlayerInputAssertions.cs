using System.IO;
using System.Text.Json;
using SyncWatch.Design;

internal static class PlayerInputAssertions
{
    internal static void Run()
    {
        using var data = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "player-input.json")));
        var defaults = data.RootElement.GetProperty("defaults");
        int count = 0;
        foreach (var row in data.RootElement.GetProperty("cases").EnumerateArray())
        {
            JsonElement Value(string key) => row.TryGetProperty(key, out var value) ? value : defaults.GetProperty(key);
            bool Flag(string key) => row.TryGetProperty(key, out var value) && value.GetBoolean();
            var model = new PlayerPresentation
            {
                State = Enum.Parse<PlayerVisualState>(Value("state").GetString()!, true),
                PositionMs = Value("positionMs").GetInt64(), DurationMs = Value("durationMs").GetInt64(),
                Volume = Value("volume").GetDouble(), SkipSeconds = Value("skipSeconds").GetInt32(),
                EnabledActions = Value("enabledActions").EnumerateArray().Select(a => a.GetString()!).ToHashSet(),
            };
            var received = new List<(string Action, double? Value)>();
            void Emit(string action, double? value) => received.Add((action, value));
            bool handled = row.GetProperty("kind").GetString() == "wheel"
                ? model.DispatchWheel(row.GetProperty("wheel").GetDouble(), Emit, Flag("modified"), Flag("protectedFocus"))
                : model.DispatchKey(row.GetProperty("key").GetString()!, Emit, Flag("repeating"), Flag("fullscreen"), Flag("modified"), Flag("protectedFocus"));
            var expected = row.GetProperty("expected").EnumerateArray().Select(e =>
                (Action: e.GetProperty("action").GetString()!, Value: e.TryGetProperty("value", out var v) ? (double?)v.GetDouble() : null)).ToArray();
            if (handled != row.GetProperty("handled").GetBoolean() || received.Count != expected.Length
                || received.Zip(expected).Any(pair => pair.First.Action != pair.Second.Action
                    || (pair.First.Value is double actual && pair.Second.Value is double value ? Math.Abs(actual - value) > .000001 : pair.First.Value != pair.Second.Value)))
                throw new InvalidOperationException("Player input: " + row.GetProperty("name").GetString());
            if (model.Volume != Value("volume").GetDouble() || model.PositionMs != Value("positionMs").GetInt64())
                throw new InvalidOperationException("Input acknowledged itself");
            count++;
        }
        if (count != 34) throw new InvalidOperationException("Incomplete input corpus");
        foreach (double value in new[] { double.NaN, double.PositiveInfinity, double.NegativeInfinity })
            if (PlayerPresentation.Gallery(PlayerVisualState.Paused).DispatchWheel(value, (_, _) => throw new InvalidOperationException("Nonfinite wheel emitted input")))
                throw new InvalidOperationException("Nonfinite wheel was consumed");
    }
}
