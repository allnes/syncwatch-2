using System.IO;
using System.Text.Json;
using SyncWatch.Bridge;
using SyncWatch.Domain;

namespace SyncWatch;

// Explicit authored-fixture check. Commands use the actual PlayerChrome controller;
// the exported observation is always read from VLC, never from command targets.
internal static class SharedPlaybackAcceptance
{
    internal static async Task RunAsync(PlaybackWorkspace controller, string file, string configuration)
    {
        using var document = JsonDocument.Parse(File.ReadAllBytes(configuration)); var config = document.RootElement;
        string Text(string key) => config.GetProperty(key).GetString() ?? throw new InvalidDataException(key);
        string runtime = Text("runtime"), executable = Text("executable"), control = Text("control"), output = Text("state");
        var endpoint = new SyncplayEndpoint(Text("host"), config.GetProperty("port").GetInt32(), Text("room"), Text("username"));
        DateTime expires = DateTime.UtcNow.AddMinutes(15);
        PlaybackObservation observation;
        do
        {
            observation = await controller.Player.ObserveAsync(controller.Scope);
            if (DateTime.UtcNow >= expires) throw new TimeoutException();
            if (observation.Status != PlaybackStatus.Ready || !observation.Seekable) await Task.Delay(40);
        } while (observation.Status != PlaybackStatus.Ready || !observation.Seekable);
        long duration = observation.DurationMs ?? throw new InvalidDataException("duration");
        string revision = File.ReadAllText(Path.Combine(runtime, "app", "syncplay-revision.txt")).Trim();
        var transport = await Task.Run(() => HelperProcess.Start(executable, runtime));
        await controller.ConnectSharedAsync(transport, endpoint,
            new("fixture-media", Path.GetFileName(file), duration, checked((ulong)new FileInfo(file).Length)), revision);
        int sequence = 0;
        while (DateTime.UtcNow < expires)
        {
            if (controller.SharedState is { } shared)
            {
                if (shared.Connection == HelperConnection.Failed) throw new IOException("Helper failed");
                var actual = await controller.Player.ObserveAsync(controller.Scope);
                byte[] value = JsonSerializer.SerializeToUtf8Bytes(new
                {
                    connection = shared.Connection.ToString().ToLowerInvariant(),
                    ready = shared.Ready,
                    acceptedUsername = shared.AcceptedUsername ?? "",
                    participants = shared.Participants?.Select(p => p.Username).ToArray(),
                    positionMs = actual.PositionMs,
                    paused = actual.Paused,
                    rate = actual.Rate,
                    sequence = actual.Sequence,
                    controlSequence = sequence,
                    guiObserved = false,
                    physicalOutputAccepted = false
                });
                string temporary = output + ".tmp"; File.WriteAllBytes(temporary, value); File.Move(temporary, output, true);
            }
            if (File.Exists(control))
            {
                using var command = JsonDocument.Parse(File.ReadAllBytes(control)); var instruction = command.RootElement;
                int next = instruction.GetProperty("sequence").GetInt32();
                if (next > sequence)
                {
                    if (next != sequence + 1) throw new InvalidDataException("sequence");
                    string action = instruction.GetProperty("action").GetString()!;
                    if (action == "finish") return;
                    if (action is not ("playPause" or "seek" or "setMovieVolume" or "muteMovie")) throw new InvalidDataException("action");
                    controller.RequestAction(action, instruction.TryGetProperty("value", out var number) ? number.GetDouble() : null);
                    sequence = next;
                }
            }
            await Task.Delay(100);
        }
        throw new TimeoutException();
    }
}
