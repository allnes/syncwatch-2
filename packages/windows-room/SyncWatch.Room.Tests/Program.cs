using System.Text;
using System.Text.Json;
using SyncWatch.Room;

using var fixture = JsonDocument.Parse(File.ReadAllBytes(args[0]));
var identity = new RoomIdentity("run-room-client", "Room User");
foreach (var entry in fixture.RootElement.GetProperty("addresses").EnumerateArray())
{
    bool valid = entry.GetProperty("valid").GetBoolean(), accepted = false;
    try { _ = new RoomAddress(entry.GetProperty("value").GetString()!); accepted = true; } catch (Exception) { }
    if (valid != accepted) throw new Exception("address: " + entry.GetProperty("value").GetString());
}
foreach (var entry in fixture.RootElement.GetProperty("admissions").EnumerateArray())
{
    bool valid = entry.GetProperty("valid").GetBoolean(), accepted = false;
    RoomAdmission? admission = null;
    try { admission = RoomAdmission.Decode(Encoding.UTF8.GetBytes(entry.GetProperty("wire").GetString()!), identity, entry.GetProperty("owner").GetBoolean()); accepted = true; }
    catch (Exception) { }
    if (valid != accepted) throw new Exception("admission: " + entry.GetProperty("name").GetString());
    if (admission is not null && (admission.MemberId != "member-owner" || admission.Bootstrap.Connection.Port != 8999
        || admission.ToString().Contains(new string('A', 64), StringComparison.Ordinal) || admission.ToString().Contains(new string('B', 64), StringComparison.Ordinal))) throw new Exception("admission facts/redaction");
}
Console.WriteLine("SYNCWATCH_ROOM_PROTOCOL_OK");
await TransportChecks.RunAsync();
