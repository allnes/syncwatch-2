using System.IO;
using System.Text;
using System.Text.Json;
using SyncWatch;
using SyncWatch.Domain;
using SyncWatch.Library;
using SyncWatch.Room;

internal static class RoomPublicationChecks
{
    internal static async Task RunAsync()
    {
        string directory = Path.Combine(Path.GetTempPath(), "syncwatch-room-publication-" + Guid.NewGuid());
        Directory.CreateDirectory(directory);
        try
        {
            File.WriteAllText(Path.Combine(directory, "Movie.mkv"), "authored metadata fixture");
            var files = await new FileSystemLibrary().ScanAsync(directory, Guid.NewGuid().ToString("D"), false);
            var map = new RoomLocalCatalog(); var publication = map.Prepare(files); string id = publication.Items.Single().MediaId;
            if (id == files.Single().Id || publication.Items.Single().Title != "Movie" || map.Prepare(files).Items.Single().MediaId != id || map.LocalId(id) is not null) throw new Exception("Pending room identity");
            map.Acknowledge(publication);
            if (map.LocalId(id) != files.Single().Id || new RoomLocalCatalog().Prepare(files).Items.Single().MediaId == id) throw new Exception("Membership-scoped room identity");
            map.Acknowledge(map.Prepare([])); if (map.LocalId(id) is not null) throw new Exception("Removed room identity");

            using var fixture = JsonDocument.Parse(File.ReadAllBytes("contracts/fixtures/room-client.json"));
            var admitted = fixture.RootElement.GetProperty("admissions").EnumerateArray().First(p => p.GetProperty("valid").GetBoolean() && p.GetProperty("owner").GetBoolean());
            var admission = RoomAdmission.Decode(Encoding.UTF8.GetBytes(admitted.GetProperty("wire").GetString()!), new("run-room-client", "Room User"), true);
            string title = string.Concat(Enumerable.Repeat("😀", 256));
            var items = Enumerable.Range(0, 100).Select(i => new MediaDescriptor($"movie-{i}", title, title, 1024, null, null)).ToArray();
            int offset = 0; long number = 1;
            do
            {
                var batch = RoomMembershipSession.CatalogCommand(admission, number++, 0, "batch-test", items, offset);
                if (batch.Count is < 1 or > 100 || batch.Command.EncodedBytes.Length > 65536) throw new Exception("Wire batch bound");
                using var wire = JsonDocument.Parse(batch.Command.EncodedBytes); var payload = wire.RootElement.GetProperty("payload");
                if (payload.GetProperty("offset").GetInt32() != offset || payload.GetProperty("items").GetArrayLength() != batch.Count || payload.GetProperty("final").GetBoolean() != (offset + batch.Count == items.Length)) throw new Exception("Wire batch facts");
                offset += batch.Count;
            } while (offset < items.Length);
            if (number <= 2 || offset != 100 || RoomMembershipSession.CatalogCommand(admission, number, 0, "batch-empty", [], 0).Count != 0) throw new Exception("Unicode batch splitting and empty clear");
            Console.WriteLine("SYNCWATCH_ROOM_PUBLICATION_MODEL_OK opaque identity/unicode byte bounds/empty clear");
        }
        finally { Directory.Delete(directory, true); }
    }
}
