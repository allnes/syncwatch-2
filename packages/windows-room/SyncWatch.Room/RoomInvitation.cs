using System.Text;

namespace SyncWatch.Room;

/// <summary>Explicit clipboard transfer. Parsing performs no network or persistence work.</summary>
public sealed class RoomInvitation
{
    public string RoomId { get; }
    public RoomSecret Credential { get; }
    public RoomInvitation(string roomId, RoomSecret credential)
    {
        RoomWire.Id(roomId); RoomId = roomId; Credential = credential;
    }
    public static RoomInvitation Parse(string text)
    {
        if (Encoding.UTF8.GetByteCount(text) > RoomWire.MaximumBytes) throw new RoomProtocolException("frameTooLarge");
        string[] lines = text.Replace("\r\n", "\n", StringComparison.Ordinal).Split('\n');
        if (lines.Length != 2) throw new RoomProtocolException("malformed");
        return new(lines[0], new RoomSecret(lines[1]));
    }
    public string CopyText() => RoomId + "\n" + Credential.CopyInvitation();
    public override string ToString() => "[redacted invitation]";
}
