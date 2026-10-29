package syncwatch

import syncwatch.design.*

internal fun watchPlaylistChecks() {
    val playlist = WatchPlaylist()
    val entries = listOf(SelectionMenuEntry("first", "Кино.One.mkv"), SelectionMenuEntry("missing", "Absent.mkv", enabled = false), SelectionMenuEntry("last", "Кино.Two.mkv"))
    playlist.update(entries, "first", true)
    check(playlist.neighbor(-1) == null && playlist.neighbor(1) == "last")
    playlist.open(); val menu = checkNotNull(playlist.menu)
    var request: SelectionMenuRequest? = null
    menu.dispatch("last", menu.contextToken) { request = it }
    val old = checkNotNull(request)
    check(playlist.selection(old) == "last")
    playlist.open(); check(playlist.menu?.selectedID == "first")
    playlist.update(entries, "last", true); playlist.open()
    check(playlist.selection(old) == null && playlist.neighbor(-1) == "first" && playlist.neighbor(1) == null)
    playlist.update(entries, "last", false); playlist.open()
    check(playlist.neighbor(-1) == null && playlist.menu?.allows("first") == false)
    playlist.update(entries + entries[0], "first", true); playlist.open()
    check(playlist.menu == null && playlist.neighbor(1) == null)
    playlist.update(entries, "removed-current", true); playlist.open()
    check(playlist.menu?.selectedID == null && playlist.menu?.allows("first") == true && playlist.selection(old) == null)
    playlist.close(); playlist.update(entries, "first", true); playlist.open()
    check(playlist.menu == null && playlist.neighbor(1) == null)
}
