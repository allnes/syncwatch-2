using System.Text;
using System.Text.Json;
using SyncWatch.Domain;
using SyncWatch.Synchronization;

using JsonDocument fixtures = JsonDocument.Parse(File.ReadAllBytes(args.Single()));
int count = 0;
foreach (var fixture in fixtures.RootElement.EnumerateArray())
{
    bool accepted;
    try
    {
        HelperWire.Decode(Encoding.UTF8.GetBytes(fixture.GetProperty("json").GetString()! + "\n"), new PlaybackScope("session-test", 2));
        accepted = true;
    }
    catch (Exception) { accepted = false; }
    if (accepted != fixture.GetProperty("accepted").GetBoolean()) throw new Exception(fixture.GetProperty("name").GetString());
    count++;
}
Console.WriteLine($"SYNCWATCH_SESSION_WIRE_OK {count}");
