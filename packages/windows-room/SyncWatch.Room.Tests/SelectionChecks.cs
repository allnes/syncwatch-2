using System.Text;
using System.Text.Json;
using SyncWatch.Room;

internal static class SelectionChecks
{
    internal static void Run(string fixture)
    {
        using var document = JsonDocument.Parse(File.ReadAllBytes(fixture));
        foreach (var entry in document.RootElement.GetProperty("cases").EnumerateArray())
        {
            var bootstrap = RoomBootstrap.Decode(Encoding.UTF8.GetBytes(entry.GetProperty("bootstrap").GetString()!));
            RoomSelectionDefinition? result = null;
            try { result = RoomSelectionDefinition.Decode(Encoding.UTF8.GetBytes(entry.GetProperty("wire").GetString()!), bootstrap); }
            catch (RoomProtocolException) { }
            if ((result is not null) != entry.GetProperty("valid").GetBoolean()) throw new Exception("selection: " + entry.GetProperty("name").GetString());
            if (result is null) continue;
            if (result.Selection?.Media.MediaId != bootstrap.Snapshot.MediaId || result.WatchGeneration != bootstrap.Snapshot.WatchGeneration
                || (result.Selection is not null && (result.Selection.MemberId != "departed-member" || result.Selection.Media.FileSizeBytes != 1000)))
                throw new Exception("frozen selection facts");
        }
        Console.WriteLine("SYNCWATCH_ROOM_SELECTION_OK");
    }
}
