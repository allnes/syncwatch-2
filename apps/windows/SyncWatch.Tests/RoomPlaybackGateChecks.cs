using SyncWatch;
using SyncWatch.Design;

internal static class RoomPlaybackGateChecks
{
    internal static async Task RunAsync()
    {
        var controller = new RoomController();
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
    }
}
