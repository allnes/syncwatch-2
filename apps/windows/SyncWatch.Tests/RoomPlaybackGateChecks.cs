using SyncWatch;
using SyncWatch.Design;

internal static class RoomPlaybackGateChecks
{
    internal static async Task RunAsync()
    {
        var controller = new RoomController();
        controller.Editor.SelectMode("joinRoom"); controller.Editor.Edit("serviceAddress", "https://rooms.example.com"); controller.Editor.Edit("username", "Peer");
        string credential = new('A', 64);
        controller.PasteInvitation("room-paste\r\n" + credential);
        if (controller.Editor.Values["roomID"] != "room-paste" || controller.Editor.Values["invitation"] != credential || !controller.Editor.IsValid || controller.Editor.Values["serviceAddress"] != "https://rooms.example.com")
            throw new InvalidOperationException("Invitation paste changed destination or failed to populate a valid draft");
        controller.Editor.State = "connecting"; controller.PasteInvitation("invalid");
        if (controller.Editor.Values["invitation"] != credential) throw new InvalidOperationException("Busy invitation draft changed");
        controller.Editor.State = "disconnected"; controller.PasteInvitation("invalid");
        if (controller.Editor.Values["invitation"] != "" || controller.Editor.Values["roomID"] != "" || controller.Editor.IsValid || controller.Editor.Status != "roomInvitationInvalid" || controller.Editor.Values["username"] != "Peer")
            throw new InvalidOperationException("Invalid invitation retained stale credentials or erased identity");
        var source = LibraryPresentation.Gallery(LibraryVisualState.Selected);
        if (!source.Allows("startWatching")) throw new InvalidOperationException("Missing local playback baseline");
        foreach (string state in new[] { "connecting", "connected", "failed" })
        {
            controller.Editor.State = state;
            if (controller.LibraryPresentation(source).Allows("startWatching")) throw new InvalidOperationException("Room attempt enabled unsynchronized playback");
            if (state == "failed" && controller.Editor.Context.Values["can.leaveRoom"] != "true") throw new InvalidOperationException("Failed room has no explicit exit");
            await controller.CloseAsync();
            if (!controller.LibraryPresentation(source).Allows("startWatching")) throw new InvalidOperationException("Explicit exit did not restore local playback");
        }
        Console.WriteLine("SYNCWATCH_ROOM_PLAYBACK_GATE_OK explicit exit after failure");
        Console.WriteLine("SYNCWATCH_ROOM_INVITATION_OK atomic paste with an explicit service destination");
    }
}
