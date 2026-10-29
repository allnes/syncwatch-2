import SyncWatchDesign
import Testing

@testable import SyncWatch

@Test @MainActor func playlistRejectsObsoleteRequestsAndRetainsObservedSelection() throws {
    let playlist = WatchPlaylist()
    let entries = [
        SelectionMenuEntry(id: "first", label: "Кино.One.mkv"),
        SelectionMenuEntry(id: "missing", label: "Absent.mkv", enabled: false),
        SelectionMenuEntry(id: "last", label: "Кино.Two.mkv"),
    ]
    playlist.update(entries: entries, selectedID: "first", enabled: true)
    #expect(playlist.neighbor(-1) == nil && playlist.neighbor(1) == "last")
    playlist.open()
    let menu = try #require(playlist.menu)
    var request: SelectionMenuRequest?
    menu.dispatch("last", contextToken: menu.contextToken) { request = $0 }
    let old = try #require(request)
    #expect(playlist.selection(old) == "last")
    // A dispatched request cannot optimistically acknowledge the native load.
    playlist.open()
    #expect(playlist.menu?.selectedID == "first")
    playlist.update(entries: entries, selectedID: "last", enabled: true)
    playlist.open()
    #expect(playlist.selection(old) == nil)
    #expect(playlist.neighbor(-1) == "first" && playlist.neighbor(1) == nil)
    playlist.update(entries: entries, selectedID: "last", enabled: false)
    playlist.open()
    #expect(playlist.neighbor(-1) == nil && playlist.menu?.allows("first") == false)
    playlist.update(entries: entries + [entries[0]], selectedID: "first", enabled: true)
    playlist.open()
    #expect(playlist.menu == nil && playlist.neighbor(1) == nil)
    playlist.update(entries: entries, selectedID: "removed-current", enabled: true)
    playlist.open()
    #expect(playlist.menu?.selectedID == nil && playlist.menu?.allows("first") == true)
    #expect(playlist.selection(old) == nil)
    playlist.close()
    playlist.update(entries: entries, selectedID: "first", enabled: true)
    playlist.open()
    #expect(playlist.menu == nil && playlist.neighbor(1) == nil)
}

@Test @MainActor func playlistMenuPermitsLocalFilesWhileNeighborsRequireRoomAvailability() throws {
    let playlist = WatchPlaylist()
    let entries = ["first", "local", "last"].map { SelectionMenuEntry(id: $0, label: $0) }
    playlist.update(entries: entries, selectedID: "first", enabled: true, neighborIDs: ["first", "last"])
    #expect(playlist.neighbor(1) == "last")
    playlist.open()
    let menu = try #require(playlist.menu)
    var request: SelectionMenuRequest?
    menu.dispatch("local", contextToken: menu.contextToken) { request = $0 }
    let local = try #require(request)
    #expect(playlist.selection(local) == "local")
    playlist.open()
    // Availability changes must invalidate a menu even when its labels are unchanged.
    playlist.update(entries: entries, selectedID: "first", enabled: true, neighborIDs: ["first", "local", "last"])
    #expect(playlist.menu == nil && playlist.neighbor(1) == "local")
    playlist.open()
    #expect(playlist.selection(local) == nil)
}
