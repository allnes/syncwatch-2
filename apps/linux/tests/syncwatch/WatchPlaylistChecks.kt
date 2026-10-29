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
    val available = WatchPlaylist()
    val localEntries = listOf("first", "local", "last").map { SelectionMenuEntry(it, it) }
    available.update(localEntries, "first", true, setOf("first", "last"))
    check(available.neighbor(1) == "last")
    available.open(); val localMenu = checkNotNull(available.menu)
    var localRequest: SelectionMenuRequest? = null
    localMenu.dispatch("local", localMenu.contextToken) { localRequest = it }
    val local = checkNotNull(localRequest)
    check(available.selection(local) == "local")
    available.open()
    available.update(localEntries, "first", true, setOf("first", "local", "last"))
    check(available.menu == null && available.neighbor(1) == "local")
    available.open(); check(available.selection(local) == null)
    playlist.update(entries, "removed-current", true); playlist.open()
    check(playlist.menu?.selectedID == null && playlist.menu?.allows("first") == true && playlist.selection(old) == null)
    playlist.close(); playlist.update(entries, "first", true); playlist.open()
    check(playlist.menu == null && playlist.neighbor(1) == null)
}
