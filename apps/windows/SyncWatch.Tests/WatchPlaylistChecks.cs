using SyncWatch;
using SyncWatch.Design;

internal static class WatchPlaylistChecks
{
    internal static void Run()
    {
        static void Require(bool value) { if (!value) throw new InvalidOperationException("playlist-selection-boundary"); }
        var playlist = new WatchPlaylist();
        SelectionMenuEntry[] entries = [new("first", "Кино.One.mkv"), new("missing", "Absent.mkv", Enabled: false), new("last", "Кино.Two.mkv")];
        playlist.Update(entries, "first", true);
        Require(playlist.Neighbor(-1) is null && playlist.Neighbor(1) == "last");
        playlist.Open(); var menu = playlist.Menu ?? throw new InvalidOperationException("playlist-menu");
        SelectionMenuRequest? request = null;
        menu.Dispatch("last", menu.ContextToken, value => request = value);
        var old = request ?? throw new InvalidOperationException("playlist-request");
        Require(playlist.Selection(old) == "last");
        playlist.Open(); Require(playlist.Menu?.SelectedID == "first");
        playlist.Update(entries, "last", true); playlist.Open();
        Require(playlist.Selection(old) is null && playlist.Neighbor(-1) == "first" && playlist.Neighbor(1) is null);
        playlist.Update(entries, "last", false); playlist.Open();
        Require(playlist.Neighbor(-1) is null && playlist.Menu?.Allows("first") == false);
        playlist.Update([.. entries, entries[0]], "first", true); playlist.Open();
        Require(playlist.Menu is null && playlist.Neighbor(1) is null);
        playlist.Update(entries, "removed-current", true); playlist.Open();
        Require(playlist.Menu?.SelectedID is null && playlist.Menu?.Allows("first") == true && playlist.Selection(old) is null);
        playlist.Close(); playlist.Update(entries, "first", true); playlist.Open();
        Require(playlist.Menu is null && playlist.Neighbor(1) is null);
    }
}
