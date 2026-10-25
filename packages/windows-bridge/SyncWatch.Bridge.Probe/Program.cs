using System.Diagnostics;
using System.Text.Json;
using SyncWatch.Bridge;
using SyncWatch.Domain;

if (args.Length == 2 && args[0] == "--player-correction-fixtures") { PlayerCorrectionChecks.Run(args[1]); return; }
PlayerCorrectionChecks.Run(Path.Combine("contracts", "fixtures", "helper-player.json"));
if (args.Length != 2) throw new ArgumentException("Pass the owned helper and runtime paths");

var commands = new HelperCommands(new PlaybackScope("native-probe", 2));

async Task<string> Read(HelperProcess helper, int seconds = 5)
{
    using CancellationTokenSource deadline = new(TimeSpan.FromSeconds(seconds));
    using JsonDocument value = JsonDocument.Parse(await helper.ReadAsync(deadline.Token));
    return value.RootElement.GetProperty("type").GetString()!;
}

await using (HelperProcess helper = HelperProcess.Start(args[0], args[1]))
{
    byte[] hello = commands.Hello(1);
    await helper.SendAsync(hello);
    if (await Read(helper, 15) != "bridge.ready") throw new IOException("Missing handshake");
    await helper.SendAsync(hello);
    if (await Read(helper) != "bridge.ready") throw new IOException("Missing duplicate response");
    await helper.SendAsync(commands.Loaded(2, "media-1", "Movie.mkv", 60000, 1234));
    if (await Read(helper) != "bridge.result") throw new IOException("Missing media acknowledgement");
    await helper.SendAsync(commands.Shutdown(3));
    if (await Read(helper) != "bridge.stopped") throw new IOException("Missing shutdown acknowledgement");
}

await using (HelperProcess helper = HelperProcess.Start(args[0], args[1]))
{
    using CancellationTokenSource cancel = new(TimeSpan.FromMilliseconds(100));
    try { await helper.ReadAsync(cancel.Token); throw new IOException("Cancellation was ignored"); }
    catch (OperationCanceledException) { }
}

await using (HelperProcess helper = HelperProcess.Start(args[0], args[1]))
{
    Process.GetProcessById(helper.ProcessId).Kill();
    try { await Read(helper); throw new IOException("Crash was ignored"); }
    catch (EndOfStreamException) { }
}

Console.WriteLine("SYNCWATCH_NATIVE_BRIDGE_OK handshake replay media shutdown cancellation crash");
