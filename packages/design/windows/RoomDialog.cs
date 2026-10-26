using System.Collections.ObjectModel;
using System.Windows.Controls;

namespace SyncWatch.Design;

/// <summary>Memory-only connection draft; never persists credentials.</summary>
public sealed class RoomEditor
{
    private readonly Dictionary<string, string> values = new(SyncWatchRoomForm.Defaults);
    public IReadOnlyDictionary<string, string> Values => new ReadOnlyDictionary<string, string>(new Dictionary<string, string>(values));
    public string Mode { get; private set; } = "createRoom";
    public string State { get; set; } = "disconnected";
    public string Status { get; set; } = "";
    public string RoomId { get; set; } = "";
    public int MemberCount { get; set; }
    public bool Owner { get; set; }
    public bool Busy => State == "connecting";
    public bool Connected => State == "connected";
    public SyncWatchRoomFormField[] Fields => SyncWatchRoomForm.Fields.Where(p => p.Section == "connection" || p.Section == Mode).ToArray();
    public RoomEditor(IReadOnlyDictionary<string, string>? initial = null)
    {
        foreach (var descriptor in SyncWatchRoomForm.Fields.Where(p => p.Kind != "secret"))
            if (initial?.TryGetValue(descriptor.Id, out var value) == true) values[descriptor.Id] = value;
    }
    public bool IsValid => Fields.All(descriptor => values.TryGetValue(descriptor.Id, out var value) && value.Length is > 0
        && value.Length <= descriptor.MaxLength && !value.Any(c => c < 32 || c == 127));
    public void Edit(string id, string value)
    {
        if (Busy || Connected || Fields.FirstOrDefault(p => p.Id == id) is not { } descriptor || value.Length > descriptor.MaxLength) return;
        values[id] = value; Status = "";
    }
    public void SelectMode(string mode)
    {
        if (Busy || Connected || mode == Mode || mode is not ("createRoom" or "joinRoom")) return;
        ClearSecrets(); Mode = mode; Status = "";
    }
    public void ClearSecrets() { foreach (var descriptor in SyncWatchRoomForm.Fields.Where(p => p.Kind == "secret")) values[descriptor.Id] = ""; }
    public DesignContext Context => new()
    {
        Values = new()
        {
            ["namespace"] = "room",
            ["showForm"] = (!Connected).ToString().ToLowerInvariant(),
            ["connected"] = Connected.ToString().ToLowerInvariant(),
            ["createMode"] = (Mode == "createRoom").ToString().ToLowerInvariant(),
            ["joinMode"] = (Mode == "joinRoom").ToString().ToLowerInvariant(),
            ["connectLabel"] = Mode,
            ["status"] = Busy ? "roomConnecting" : Status,
            ["roomID"] = RoomId,
            ["memberCount"] = MemberCount.ToString(System.Globalization.CultureInfo.InvariantCulture),
            ["can.close"] = "true",
            ["can.chooseRoomMode"] = (!Busy && !Connected).ToString().ToLowerInvariant(),
            ["can.connectRoom"] = (!Busy && !Connected && IsValid).ToString().ToLowerInvariant(),
            ["can.leaveRoom"] = Connected.ToString().ToLowerInvariant(),
            ["can.copyInvitation"] = (Connected && Owner).ToString().ToLowerInvariant()
        },
        Collections = new()
        {
            ["fields"] = Fields.Select(p => new DesignContext
            {
                Values = new()
                {
                    ["id"] = p.Id,
                    ["label"] = p.Label,
                    ["value"] = values[p.Id],
                    ["secret"] = (p.Kind == "secret").ToString().ToLowerInvariant(),
                    ["editable"] = (!Busy).ToString().ToLowerInvariant()
                }
            }).ToArray()
        }
    };
}
public sealed class RoomDialog : UserControl
{
    public RoomEditor Editor { get; }
    private readonly DesignSurface surface = new("Room");
    public string UiLanguage { get; private set; }
    public event Action<string>? ActionRequested;
    public RoomDialog(RoomEditor editor, string language = "en")
    {
        Editor = editor; UiLanguage = language; Content = surface; surface.ConfigureHost(this);
        surface.EventRequested += e =>
        {
            if (e.Action == "editRoomField" && e.Payload is string id && e.Value is string value) Editor.Edit(id, value);
            else if (e.Action == "chooseRoomMode" && e.Payload is string mode) Editor.SelectMode(mode);
            else ActionRequested?.Invoke(e.Action);
            Refresh();
        };
        Refresh();
    }
    public void Refresh() => surface.Render(Editor.Context, UiLanguage);
}
