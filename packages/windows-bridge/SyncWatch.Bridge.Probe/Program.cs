using System.Diagnostics;
using System.Text.Json;
using SyncWatch.Bridge;

if (args.Length != 2) throw new ArgumentException("Pass the owned helper and runtime paths");

byte[] Command(int id, string type, object payload) => JsonSerializer.SerializeToUtf8Bytes(new
{
    v = 1,
    id = "cmd-" + id,
    type,
    clientRunId = "native-probe",
    mediaGeneration = 2,
    payload
}).Concat(new byte[] { 10 }).ToArray();

async Task<string> Read(HelperProcess helper)
{
    using CancellationTokenSource deadline = new(TimeSpan.FromSeconds(5));
    using JsonDocument value = JsonDocument.Parse(await helper.ReadAsync(deadline.Token));
    return value.RootElement.GetProperty("type").GetString()!;
}

await using (HelperProcess helper = HelperProcess.Start(args[0], args[1]))
{
    byte[] hello = Command(1, "bridge.hello", new { supportedVersions = new[] { 1 } });
    await helper.SendAsync(hello);
    if (await Read(helper) != "bridge.ready") throw new IOException("Missing handshake");
    await helper.SendAsync(hello);
    if (await Read(helper) != "bridge.ready") throw new IOException("Missing duplicate response");
    await helper.SendAsync(Command(2, "player.loaded", new { mediaHandle = "media-1", name = "Movie.mkv", durationMs = 60000, fileSizeBytes = 1234 }));
    if (await Read(helper) != "bridge.result") throw new IOException("Missing media acknowledgement");
    await helper.SendAsync(Command(3, "bridge.shutdown", new { }));
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
