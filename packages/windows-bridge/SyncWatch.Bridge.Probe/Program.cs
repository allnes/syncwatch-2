using System.Diagnostics;
using SyncWatch.Bridge;
using SyncWatch.Domain;

if (args.Length == 2 && args[0] == "--player-correction-fixtures") { PlayerCorrectionChecks.Run(args[1]); return; }
PlayerCorrectionChecks.Run(Path.Combine("contracts", "fixtures", "helper-player.json"));
if (args.Length != 2) throw new ArgumentException("Pass the owned helper and runtime paths");

var wireScope = new PlaybackScope("native-probe", 2);
var commands = new HelperCommands(wireScope);
string revision = File.ReadAllText(Path.Combine(args[1], "app", "syncplay-revision.txt")).Trim();

async Task<HelperReply> Read(HelperProcess helper, ulong id, HelperReplyKind expected, int seconds = 5)
{
    using CancellationTokenSource deadline = new(TimeSpan.FromSeconds(seconds));
    return HelperReply.Decode(await helper.ReadAsync(deadline.Token), wireScope, id, expected, revision);
}

await using (HelperProcess helper = HelperProcess.Start(args[0], args[1]))
{
    byte[] hello = commands.Hello(1);
    await helper.SendAsync(hello);
    if ((await Read(helper, 1, HelperReplyKind.Ready, 15)).Kind != HelperReplyKind.Ready) throw new IOException("Missing handshake");
    await helper.SendAsync(hello);
    if ((await Read(helper, 1, HelperReplyKind.Ready)).Kind != HelperReplyKind.Ready) throw new IOException("Missing duplicate response");
    await helper.SendAsync(commands.Loaded(2, "media-1", "Movie.mkv", 60000, 1234));
    if ((await Read(helper, 2, HelperReplyKind.Applied)).Kind != HelperReplyKind.Applied) throw new IOException("Missing media acknowledgement");
    await helper.SendAsync(commands.Shutdown(3));
    if ((await Read(helper, 3, HelperReplyKind.Stopped)).Kind != HelperReplyKind.Stopped) throw new IOException("Missing shutdown acknowledgement");
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
    try { await Read(helper, 1, HelperReplyKind.Ready); throw new IOException("Crash was ignored"); }
    catch (EndOfStreamException) { }
}

Console.WriteLine("SYNCWATCH_NATIVE_BRIDGE_OK handshake replay media shutdown cancellation crash");
